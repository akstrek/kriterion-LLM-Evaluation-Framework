"""Fallback path tests. call_model is exercised with a mock OpenAI client."""
from unittest.mock import MagicMock

import pytest
from openai import RateLimitError

import config.llm as llm
from config.llm import (
    CallResult,
    FALLBACK_MAP,
    HTBTree,
    AdaptiveThrottle,
    call_model,
)


def _make_isolated_tree() -> HTBTree:
    """Fresh tree with generous tokens so HTB doesn't gate the test."""
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


def _rate_limit_error(msg="rate limited"):
    return RateLimitError(
        message=msg,
        response=MagicMock(status_code=429),
        body=None,
    )


def test_fallback_triggered_when_primary_keeps_429ing():
    """Primary returns 429 on every attempt; fallback succeeds.
    Verify CallResult.fallback_triggered=True and the fallback's provider
    is the one that gets debited, not the primary's."""
    tree = _make_isolated_tree()
    throttle = AdaptiveThrottle(tree)

    primary = "moonshotai/kimi-k2.6:free"
    fallback = FALLBACK_MAP[primary]      # "google/gemma-4-26b-a4b-it:free"
    assert fallback.startswith("google/")

    call_log: list[str] = []
    def create(model, **_kw):
        call_log.append(model)
        if model == primary:
            raise _rate_limit_error()
        return _fake_chat_completion("fallback OK", tokens=42)

    client = MagicMock()
    client.chat.completions.create.side_effect = create

    # Skip the retry sleep so the test runs fast.
    import unittest.mock as um
    with um.patch.object(llm, "_interruptible_sleep", lambda s: None):
        result = call_model(
            primary,
            [{"role": "user", "content": "hi"}],
            role="evaluator",
            tree=tree, throttle=throttle, client=client,
        )

    assert isinstance(result, CallResult)
    assert result.fallback_triggered is True
    # model_used reflects the model actually called (the fallback).
    assert result.model_used == fallback
    assert result.tokens_used == 42

    # Primary called MAX_RETRY=2 times, fallback once.
    primary_calls = [m for m in call_log if m == primary]
    fb_calls      = [m for m in call_log if m == fallback]
    assert len(primary_calls) == llm.MAX_RETRY
    assert len(fb_calls) == 1

    # HTB: primary's provider (moonshotai) debited twice; fallback's (google) once.
    moonshot_used = 100 - tree.providers["moonshotai"].daily_remaining
    google_used   = 100 - tree.providers["google"].daily_remaining
    assert moonshot_used == llm.MAX_RETRY
    assert google_used == 1


def test_fallback_not_used_when_primary_succeeds():
    tree = _make_isolated_tree()
    throttle = AdaptiveThrottle(tree)
    primary = "openai/gpt-oss-120b:free"

    client = MagicMock()
    client.chat.completions.create.return_value = _fake_chat_completion("ok", tokens=10)

    result = call_model(
        primary, [{"role": "user", "content": "hi"}], role="evaluator",
        tree=tree, throttle=throttle, client=client,
    )
    assert result.fallback_triggered is False
    assert result.retry_count == 0
    assert result.tokens_used == 10
    # Only the primary's provider was debited.
    openai_used = 100 - tree.providers["openai"].daily_remaining
    assert openai_used == 1


def test_retry_count_increments_on_transient_error():
    tree = _make_isolated_tree()
    throttle = AdaptiveThrottle(tree)
    primary = "openai/gpt-oss-120b:free"

    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _rate_limit_error(),
        _fake_chat_completion("ok-on-retry", tokens=5),
    ]

    import unittest.mock as um
    with um.patch.object(llm, "_interruptible_sleep", lambda s: None):
        result = call_model(
            primary, [{"role": "user", "content": "hi"}], role="evaluator",
            tree=tree, throttle=throttle, client=client,
        )

    assert result.retry_count == 1
    assert result.fallback_triggered is False
    assert client.chat.completions.create.call_count == 2
