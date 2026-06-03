"""Retry-timing + retry-class tests for config.llm.

Covers the 429-resilience fix: Retry-After / X-RateLimit-Reset honoring,
full-jitter exponential backoff, and retry-class discrimination (429/5xx/timeout
retried; 4xx / empty failed fast). No real network calls.
"""
import time
from unittest.mock import MagicMock

import unittest.mock as um
from openai import (
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    RateLimitError,
)

import config.llm as llm
from config.llm import (
    AdaptiveThrottle,
    CallResult,
    DailyQuotaExhausted,
    FALLBACK_MAP,
    HTBTree,
    _compute_backoff,
    _retry_after_seconds,
    call_model,
    is_retryable,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_isolated_tree() -> HTBTree:
    tree = HTBTree()
    with tree.lock:
        for n in [tree.root, *tree.providers.values()]:
            n.tokens = 100.0
            n.daily_remaining = 100
            n.daily_budget = 100
    return tree


def _fake_chat_completion(text: str, tokens: int = 7):
    resp = MagicMock()
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp.choices = [choice]
    usage = MagicMock()
    usage.total_tokens = tokens
    resp.usage = usage
    return resp


def _status_error(cls, status: int, headers: dict | None = None):
    resp = MagicMock(status_code=status, headers=headers if headers is not None else {})
    return cls(message="boom", response=resp, body=None)


# ── _retry_after_seconds ───────────────────────────────────────────────────────

def test_retry_after_header_preferred():
    exc = _status_error(RateLimitError, 429, {"retry-after": "5"})
    assert _retry_after_seconds(exc) == 5.0


def test_x_ratelimit_reset_epoch_ms_used():
    reset_ms = (time.time() + 8.0) * 1000.0
    exc = _status_error(RateLimitError, 429, {"x-ratelimit-reset": str(reset_ms)})
    secs = _retry_after_seconds(exc)
    assert secs is not None
    assert 7.0 < secs <= 8.5


def test_no_headers_returns_none():
    # Timeout / connection errors carry no `.response` headers.
    assert _retry_after_seconds(APITimeoutError(request=MagicMock())) is None
    # A 429 with no recognized headers also yields None → caller uses backoff.
    assert _retry_after_seconds(_status_error(RateLimitError, 429, {})) is None


def test_unparseable_header_falls_through():
    exc = _status_error(RateLimitError, 429, {"retry-after": "not-a-number"})
    assert _retry_after_seconds(exc) is None


# ── _compute_backoff ───────────────────────────────────────────────────────────

def test_compute_backoff_honors_server_header():
    exc = _status_error(RateLimitError, 429, {"retry-after": "5"})
    for _ in range(50):
        d = _compute_backoff(exc, attempt=0)
        # base 5 + jitter in [0, 1]
        assert 5.0 <= d <= 6.0


def test_compute_backoff_clamps_hostile_header():
    exc = _status_error(RateLimitError, 429, {"retry-after": "99999"})
    for _ in range(50):
        assert _compute_backoff(exc, attempt=0) <= llm._BACKOFF_CAP


def test_compute_backoff_full_jitter_bounded():
    exc = _status_error(RateLimitError, 429, {})  # header-less → full jitter
    for attempt in range(0, 3):
        ceiling = min(llm._BACKOFF_CAP, llm._BACKOFF_BASE * (2 ** attempt))
        for _ in range(50):
            d = _compute_backoff(exc, attempt=attempt)
            assert 0.0 <= d <= ceiling


def test_compute_backoff_varies_across_draws():
    exc = _status_error(RateLimitError, 429, {})
    draws = {round(_compute_backoff(exc, attempt=2), 6) for _ in range(20)}
    assert len(draws) > 1  # jitter de-correlates the worker threads


# ── is_retryable ───────────────────────────────────────────────────────────────

def test_is_retryable_classes():
    assert is_retryable(_status_error(RateLimitError, 429)) is True
    assert is_retryable(_status_error(InternalServerError, 500)) is True
    assert is_retryable(_status_error(InternalServerError, 503)) is True
    assert is_retryable(APITimeoutError(request=MagicMock())) is True
    assert is_retryable(APIConnectionError(request=MagicMock())) is True

    assert is_retryable(_status_error(BadRequestError, 400)) is False
    assert is_retryable(_status_error(NotFoundError, 404)) is False
    assert is_retryable(DailyQuotaExhausted("nope")) is False
    assert is_retryable(ValueError("empty choices")) is False


# ── call_model integration ─────────────────────────────────────────────────────

def test_4xx_fails_fast_no_retry_no_sleep():
    """A 4xx on the primary must not retry; it drops straight to the fallback
    hop, and no backoff sleep is incurred."""
    tree = _make_isolated_tree()
    throttle = AdaptiveThrottle(tree)
    primary = "openai/gpt-oss-120b:free"
    fallback = FALLBACK_MAP[primary]

    call_log: list[str] = []

    def create(model, **_kw):
        call_log.append(model)
        if model == primary:
            raise _status_error(BadRequestError, 400)
        return _fake_chat_completion("fallback OK", tokens=11)

    client = MagicMock()
    client.chat.completions.create.side_effect = create

    sleep_calls = {"n": 0}
    def _no_sleep(_s):
        sleep_calls["n"] += 1

    with um.patch.object(llm, "_interruptible_sleep", _no_sleep):
        result = call_model(
            primary, [{"role": "user", "content": "hi"}], role="evaluator",
            tree=tree, throttle=throttle, client=client,
        )

    assert isinstance(result, CallResult)
    assert result.fallback_triggered is True
    assert result.model_used == fallback
    # Primary tried exactly once (no retry), fallback once.
    assert [m for m in call_log if m == primary] == [primary]
    assert [m for m in call_log if m == fallback] == [fallback]
    # No backoff sleep was incurred on the fail-fast path.
    assert sleep_calls["n"] == 0


def test_5xx_retried_then_fallback():
    """A 5xx is retryable: primary is attempted MAX_RETRY times (with backoff
    sleeps between), then the fallback hop succeeds."""
    tree = _make_isolated_tree()
    throttle = AdaptiveThrottle(tree)
    primary = "openai/gpt-oss-120b:free"
    fallback = FALLBACK_MAP[primary]

    call_log: list[str] = []

    def create(model, **_kw):
        call_log.append(model)
        if model == primary:
            raise _status_error(InternalServerError, 503)
        return _fake_chat_completion("fallback OK", tokens=5)

    client = MagicMock()
    client.chat.completions.create.side_effect = create

    sleep_calls = {"n": 0}
    with um.patch.object(llm, "_interruptible_sleep", lambda _s: sleep_calls.__setitem__("n", sleep_calls["n"] + 1)):
        result = call_model(
            primary, [{"role": "user", "content": "hi"}], role="evaluator",
            tree=tree, throttle=throttle, client=client,
        )

    assert result.fallback_triggered is True
    assert len([m for m in call_log if m == primary]) == llm.MAX_RETRY
    assert len([m for m in call_log if m == fallback]) == 1
    # One backoff sleep before each retry attempt (MAX_RETRY - 1 of them).
    assert sleep_calls["n"] == llm.MAX_RETRY - 1
