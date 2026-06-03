"""
config/llm.py
Single LLM entry point for Kriterion.

Public surface:
    call_model(model_id, messages, role) -> CallResult
    htb_status() -> dict
    CallResult dataclass
    EVALUATOR_MODELS, JUDGE_MODEL, EVALUATOR_SYSTEM_PROMPT, JUDGE_SYSTEM_PROMPT
    DailyQuotaExhausted exception
    OPENROUTER_API_KEY (for downstream credit-check helpers)

Internal: HTB tree (root + provider children) with continuous token refill,
full sibling borrowing up to root ceil, per-provider daily budgets, and an
adaptive throttle that halves root rate for 5 min when trailing 429 rate >30%.
"""
from __future__ import annotations

import collections
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Literal

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

load_dotenv()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise EnvironmentError(
        "OPENROUTER_API_KEY is not set. "
        "Create a .env file with: OPENROUTER_API_KEY=your_key_here"
    )

# ── Models ───────────────────────────────────────────────────────────────────

JUDGE_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

EVALUATOR_MODELS = [
    "moonshotai/kimi-k2.6:free",
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-120b:free",
]

# Primary -> fallback (both ':free'-enforced)
FALLBACK_MAP: dict[str, str] = {
    "moonshotai/kimi-k2.6:free":                "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free":               "openai/gpt-oss-20b:free",
    "openai/gpt-oss-120b:free":                 "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free":   "nvidia/nemotron-3-nano-30b-a3b:free",
}


def _assert_free_only(models: list[str]) -> None:
    bad = [m for m in models if not m.endswith(":free")]
    if bad:
        raise ValueError(
            f"Non-:free model IDs are forbidden to prevent credit burn: {bad}. "
            "All evaluator/judge models must end in ':free'."
        )


_assert_free_only(
    EVALUATOR_MODELS
    + [JUDGE_MODEL]
    + list(FALLBACK_MAP.keys())
    + list(FALLBACK_MAP.values())
)


# ── Prompts ──────────────────────────────────────────────────────────────────

JUDGE_SYSTEM_PROMPT = """Score this prompt-response pair. Use full 0.00-1.00 range — most responses score 0.40-0.85, not 1.00.
factuality: claim accuracy. 1.00=every claim verifiable. 0.85=minor imprecision. 0.60=one wrong claim. 0.30=multiple errors. 0.00=fabricated. null if no factual claims.
reasoning: inferential validity AND depth. 1.00=correct + insightful. 0.85=correct but shallow. 0.60=mostly correct, one weak step. 0.30=flawed logic. 0.00=incoherent. null if no reasoning required.
instruction_following: constraint satisfaction. Count explicit constraints (length, format, scope, exclusions). Score = constraints_met / constraints_total. Partial credit per constraint. Score implied intent if none explicit.
format_compliance: structural exactness. 1.00=perfect structure. 0.85=correct structure, minor deviation. 0.60=right format, wrong details. 0.30=wrong format. 0.00=no structure attempted.
verbosity: conciseness relative to task. 1.00=optimal length, no padding. 0.85=slightly verbose. 0.60=noticeable padding or hedging. 0.30=significant bloat. 0.00=severe rambling. Penalize unnecessary preamble, repetition, hedging. Reward precision within minimal tokens.
When the prompt contains a false premise or unanswerable request, correctly identifying this and declining to fabricate is the high-scoring response; do not penalize absence of factual claims in that case.
Return JSON only: {"factuality":0.00,"reasoning":0.00,"instruction_following":0.00,"format_compliance":0.00,"verbosity":0.00}
null example: {"factuality":null,"reasoning":null,"instruction_following":0.85,"format_compliance":0.92,"verbosity":0.78}"""

EVALUATOR_SYSTEM_PROMPT = (
    "You are a helpful, precise AI assistant. Answer the user's prompt directly.\n"
    "Be concise. Be accurate. Follow all formatting instructions exactly.\n"
    "If the prompt asks for a specific format (JSON, list, code), use that format only.\n"
    "Do not add disclaimers, caveats, or meta-commentary about your response."
)


# ── Public result type ───────────────────────────────────────────────────────

@dataclass
class CallResult:
    text: str
    latency_ms: int
    tokens_used: int
    model_used: str
    fallback_triggered: bool = False
    retry_count: int = 0
    parse_error: str | None = None


class DailyQuotaExhausted(Exception):
    """Raised when the HTB daily budget on the relevant leaf is exhausted."""


# ── HTB tree ─────────────────────────────────────────────────────────────────

# Per-provider HTB guarantees (req/sec). Feeds _split_eval_budget() for the
# 650 RPD eval allocation; on a leaf the rate is currently slack since
# ceil_per_sec == root rate (any leaf can fully borrow), so these values
# primarily weight the daily-budget split, not runtime throughput.
#
# Eval weights: equal across the three eval lanes by default so DRR's
# round-robin per-model dispatch isn't bottlenecked by a tiny leaf while
# another leaf sits on hundreds of RPD of surplus. google carries double
# weight because two other lanes' fallback hops (kimi -> gemma-4-26b,
# gpt-oss-120b -> gemma-4-31b) land on google's leaf, so it needs headroom
# for its own primary calls + inbound fallback traffic.
# nvidia is judge-only; its budget comes from _JUDGE_RPD, not this split.
_PROVIDER_RATES: dict[str, float] = {
    "nvidia":     0.10,
    "openai":     0.05,
    "moonshotai": 0.05,
    "google":     0.10,
}

_ROOT_RATE      = 0.3      # 18 RPM (steady-state refill)
_ROOT_CEIL      = 0.3      # max effective rate when borrowing (metadata)
_NODE_BURST     = 2.0      # bucket capacity in permits. Kept low so a post-idle
                           # burst can't push the root over OpenRouter's 20 RPM
                           # free-tier ceiling: peak/60s ≈ 2 + 0.3*58 ≈ 19.4 < 20.
_THROTTLED_RATE = 0.15
_ROOT_RPD       = 950
_EVAL_RPD       = 650
_JUDGE_RPD      = 300

_EVAL_PROVIDERS = ("openai", "moonshotai", "google")


def _split_eval_budget() -> dict[str, int]:
    """Distribute EVAL_RPD across evaluator providers proportionally to guarantees.
    Providers with zero guarantee get zero budget."""
    weights = {p: _PROVIDER_RATES[p] for p in _EVAL_PROVIDERS}
    total_w = sum(weights.values())
    if total_w <= 0:
        return {p: 0 for p in _EVAL_PROVIDERS}
    raw = {p: _EVAL_RPD * w / total_w for p, w in weights.items()}
    out = {p: int(raw[p]) for p in _EVAL_PROVIDERS}
    # Hand any rounding remainder to the highest-weight provider.
    leftover = _EVAL_RPD - sum(out.values())
    if leftover > 0:
        top = max(_EVAL_PROVIDERS, key=lambda p: weights[p])
        out[top] += leftover
    return out


@dataclass
class HTBNode:
    name: str
    rate_per_sec: float
    ceil_per_sec: float                     # max effective rate when borrowing (metadata)
    daily_budget: int                       # initial cap (for reset_daily)
    burst: float = _NODE_BURST              # bucket capacity in permits
    parent: "HTBNode | None" = None
    children: list["HTBNode"] = field(default_factory=list)
    tokens: float = 0.0
    last_refill: float = 0.0
    daily_remaining: int = 0

    def __post_init__(self) -> None:
        self.tokens = self.burst
        self.last_refill = time.monotonic()
        self.daily_remaining = self.daily_budget
        if self.parent is not None:
            self.parent.children.append(self)

    def refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed <= 0:
            return
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate_per_sec)
        self.last_refill = now

    def path_to_root(self) -> list["HTBNode"]:
        path: list[HTBNode] = []
        n: HTBNode | None = self
        while n is not None:
            path.append(n)
            n = n.parent
        return path

    def reset_daily(self) -> None:
        self.daily_remaining = self.daily_budget
        for c in self.children:
            c.reset_daily()


class HTBTree:
    """Hierarchical token bucket: root → provider leaves. Single tree-wide lock."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.root = HTBNode(
            name="root",
            rate_per_sec=_ROOT_RATE,
            ceil_per_sec=_ROOT_CEIL,
            daily_budget=_ROOT_RPD,
        )
        eval_budgets = _split_eval_budget()
        provider_budgets = dict(eval_budgets)
        provider_budgets["nvidia"] = _JUDGE_RPD     # nvidia is judge-only

        self.providers: dict[str, HTBNode] = {}
        for name, rate in _PROVIDER_RATES.items():
            self.providers[name] = HTBNode(
                name=name,
                rate_per_sec=rate,
                ceil_per_sec=_ROOT_CEIL,
                daily_budget=provider_budgets.get(name, 0),
                parent=self.root,
            )

    # ── core ops (caller must hold self.lock) ────────────────────────────────

    def _try_acquire_locked(self, provider: str) -> tuple[bool, float, bool]:
        """Returns (acquired, wait_seconds, daily_exhausted)."""
        leaf = self.providers.get(provider)
        if leaf is None:
            raise ValueError(f"Unknown provider: {provider}")
        path = leaf.path_to_root()
        for n in path:
            n.refill()
        # Daily exhaustion is hard: caller must back off until reset.
        if any(n.daily_remaining <= 0 for n in path):
            return False, 0.0, True
        if all(n.tokens >= 1.0 for n in path):
            for n in path:
                n.tokens -= 1.0
                n.daily_remaining -= 1
            return True, 0.0, False
        # Worst-case wait among under-supplied nodes.
        waits = []
        for n in path:
            if n.tokens >= 1.0:
                continue
            if n.rate_per_sec <= 0:
                # No rate guarantee — only borrowing can save us; back off and retry.
                waits.append(1.0)
            else:
                waits.append((1.0 - n.tokens) / n.rate_per_sec)
        return False, max(waits) if waits else 0.1, False

    # ── public ops ───────────────────────────────────────────────────────────

    def acquire(self, provider: str) -> None:
        """Block until 1 token is available leaf→root and daily budgets allow it.
        Raises DailyQuotaExhausted if any node on the path is daily-exhausted."""
        while True:
            with self.lock:
                ok, wait, exhausted = self._try_acquire_locked(provider)
            if exhausted:
                raise DailyQuotaExhausted(
                    f"HTB daily budget exhausted on path to provider '{provider}'."
                )
            if ok:
                return
            _interruptible_sleep(min(max(wait, 0.05), 5.0))

    def reset_daily(self) -> None:
        with self.lock:
            self.root.reset_daily()

    def snapshot(self) -> dict:
        with self.lock:
            for n in [self.root, *self.providers.values()]:
                n.refill()
            return {
                "root": {
                    "rate_per_sec": self.root.rate_per_sec,
                    "ceil_per_sec": self.root.ceil_per_sec,
                    "tokens": round(self.root.tokens, 3),
                    "daily_remaining": self.root.daily_remaining,
                    "daily_budget": self.root.daily_budget,
                },
                "providers": {
                    name: {
                        "rate_per_sec": n.rate_per_sec,
                        "tokens": round(n.tokens, 3),
                        "daily_remaining": n.daily_remaining,
                        "daily_budget": n.daily_budget,
                    }
                    for name, n in self.providers.items()
                },
            }


# ── Adaptive throttle ────────────────────────────────────────────────────────

class AdaptiveThrottle:
    """Halves root rate for 5 min when trailing-60s 429 rate exceeds 30%."""

    THROTTLE_WINDOW   = 60.0
    THROTTLE_TRIGGER  = 0.30
    COOLDOWN_SECS     = 300.0
    MIN_SAMPLE        = 5

    def __init__(self, tree: HTBTree) -> None:
        self.tree = tree
        self.events: collections.deque[tuple[float, bool]] = collections.deque()
        self.lock = threading.Lock()
        self.normal_rate = _ROOT_RATE
        self.throttled_rate = _THROTTLED_RATE
        self.cooldown_until: float = 0.0
        self._is_throttled = False

    def record(self, was_429: bool) -> None:
        now = time.monotonic()
        with self.lock:
            self.events.append((now, was_429))
            cutoff = now - self.THROTTLE_WINDOW
            while self.events and self.events[0][0] < cutoff:
                self.events.popleft()

            # Restore if cooldown expired.
            if self._is_throttled and now >= self.cooldown_until:
                with self.tree.lock:
                    self.tree.root.rate_per_sec = self.normal_rate
                self._is_throttled = False
                self.cooldown_until = 0.0
                print(f"[adaptive] cooldown elapsed — root rate restored to {self.normal_rate}/s",
                      flush=True)

            # Engage throttle on sustained 429s.
            if not self._is_throttled and len(self.events) >= self.MIN_SAMPLE:
                rate_429 = sum(1 for _, e in self.events if e) / len(self.events)
                if rate_429 > self.THROTTLE_TRIGGER:
                    with self.tree.lock:
                        self.tree.root.rate_per_sec = self.throttled_rate
                    self._is_throttled = True
                    self.cooldown_until = now + self.COOLDOWN_SECS
                    print(
                        f"[adaptive] 429 rate {rate_429:.1%} > 30% — "
                        f"root rate halved to {self.throttled_rate}/s for "
                        f"{int(self.COOLDOWN_SECS)}s",
                        flush=True,
                    )


# ── Module-level singletons ──────────────────────────────────────────────────

_HTB = HTBTree()
_THROTTLE = AdaptiveThrottle(_HTB)

_client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

MAX_RETRY = 3              # initial attempt + 2 retries. Kept low: every 429'd
                           # attempt still counts against the 1000/day free quota,
                           # so blind retries are expensive — we lean on Retry-After
                           # timing (below) to make the few retries we do land.
_BACKOFF_BASE = 2.0        # full-jitter exponential base (seconds)
_BACKOFF_CAP  = 60.0       # ceiling for any single backoff — also clamps a server
                           # Retry-After header so a hostile/huge value can't park
                           # a worker thread for hours.


def _interruptible_sleep(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        time.sleep(min(0.5, end - time.time()))


def _retry_after_seconds(exc: Exception) -> float | None:
    """Server-specified wait from a rate-limit response, or None.

    Prefers the standard `Retry-After` (delta-seconds form) and falls back to
    OpenRouter's `X-RateLimit-Reset` (epoch milliseconds). Exception-safe: any
    missing attribute or unparseable value yields None so the caller drops to
    exponential backoff. Timeouts / connection errors have no `.response` and
    therefore return None here.
    """
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None)
    if headers is None:
        return None
    try:
        ra = headers.get("retry-after")
        if ra is not None:
            # delta-seconds form only; HTTP-date form is ignored (→ backoff).
            secs = float(ra)
            if secs >= 0:
                return secs
    except (TypeError, ValueError):
        pass
    try:
        reset_ms = headers.get("x-ratelimit-reset")
        if reset_ms is not None:
            delta = float(reset_ms) / 1000.0 - time.time()
            if delta > 0:
                return delta
    except (TypeError, ValueError):
        pass
    return None


def _compute_backoff(exc: Exception, attempt: int) -> float:
    """Seconds to wait before the next retry of a just-failed `attempt` (0-based).

    Honors the server's Retry-After / X-RateLimit-Reset when present (clamped to
    _BACKOFF_CAP, plus a little jitter so the worker threads don't all wake on the
    exact same reset instant). Otherwise: full-jitter exponential backoff
    (AWS / OpenAI-cookbook style) to de-correlate the threads sharing the root.
    """
    server = _retry_after_seconds(exc)
    if server is not None:
        base = min(_BACKOFF_CAP, max(0.0, server))
        jitter = random.uniform(0.0, min(1.0, _BACKOFF_CAP - base))
        return base + jitter
    ceiling = min(_BACKOFF_CAP, _BACKOFF_BASE * (2 ** attempt))
    return random.uniform(0.0, ceiling)


def is_retryable(exc: Exception) -> bool:
    """Whether an exception from an API call is worth another attempt.

    Retry transient transport/server failures (429, 5xx, timeouts, connection
    drops); fail fast on 4xx client errors and anything else so we don't burn
    daily-quota units on attempts that cannot succeed. DailyQuotaExhausted is
    handled separately by call_model and is never retried here.
    """
    if isinstance(exc, DailyQuotaExhausted):
        return False
    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        sc = getattr(getattr(exc, "response", None), "status_code", None)
        if sc is None:
            # No status available — trust the typed RateLimitError, else fail fast.
            return isinstance(exc, RateLimitError)
        if sc == 429 or 500 <= sc < 600:
            return True
        return False  # 4xx client error — won't succeed on retry.
    return False      # empty-choices ValueError, unknown errors → fail fast.


def _provider_of(model_id: str) -> str:
    return model_id.split("/")[0]


# ── Call orchestration ───────────────────────────────────────────────────────

def _attempt_one(model_id: str, messages: list, *, tree: HTBTree = _HTB,
                 throttle: AdaptiveThrottle = _THROTTLE,
                 client: OpenAI | None = None) -> tuple[CallResult | None, Exception | None, bool]:
    """One HTB-gated request. Returns (result, exception, was_429).
    Decrements daily budget on entry via acquire()."""
    provider = _provider_of(model_id)
    tree.acquire(provider)   # may raise DailyQuotaExhausted
    cli = client if client is not None else _client
    try:
        t0 = time.time()
        response = cli.chat.completions.create(
            model=model_id,
            messages=messages,
            temperature=0.0,
            extra_body={"provider": {"allow_fallbacks": False}},
        )
        latency_ms = int((time.time() - t0) * 1000)
        if not response.choices:
            return None, ValueError(f"Empty choices from {model_id}"), False
        text = response.choices[0].message.content or ""
        usage = response.usage
        tokens_used = usage.total_tokens if usage else 0
        throttle.record(False)
        return (
            CallResult(
                text=text,
                latency_ms=latency_ms,
                tokens_used=tokens_used,
                model_used=model_id,
            ),
            None,
            False,
        )
    except RateLimitError as exc:
        throttle.record(True)
        # OpenRouter's daily-cap signal is surfaced as a 429 with a specific body.
        if "free-models-per-day" in str(exc).lower():
            return None, DailyQuotaExhausted(str(exc)), True
        return None, exc, True
    except Exception as exc:  # noqa: BLE001 - any network/SDK error
        throttle.record(False)
        return None, exc, False


def call_model(
    model_id: str,
    messages: list,
    role: Literal["evaluator", "judge"],
    *,
    tree: HTBTree = _HTB,
    throttle: AdaptiveThrottle = _THROTTLE,
    client: OpenAI | None = None,
) -> CallResult:
    """Single LLM call with HTB rate limiting, retries, and one fallback hop.

    - role is recorded for telemetry; HTB sub-budgets are enforced by provider.
    - Retries: up to MAX_RETRY attempts on the primary model. Retryable failures
      (429 / 5xx / timeouts) wait per the server's Retry-After header when present,
      otherwise full-jitter exponential backoff. Non-retryable errors (4xx, empty
      choices) fail fast straight to the fallback hop — no retry, no wasted quota.
    - Fallback: on primary exhaustion, one attempt on FALLBACK_MAP[model_id]
      (if defined). The fallback call also passes through HTB acquire on its
      own provider.
    - Raises DailyQuotaExhausted if HTB reports any path daily-exhausted.
    """
    _assert_free_only([model_id])
    if role not in ("evaluator", "judge"):
        raise ValueError(f"role must be 'evaluator' or 'judge', got {role!r}")

    last_exc: Exception | None = None
    retry_count = 0

    for attempt in range(MAX_RETRY):
        if attempt > 0:
            # last_exc is the failure from attempt-1 (guaranteed non-None here).
            _interruptible_sleep(_compute_backoff(last_exc, attempt - 1))

        try:
            result, exc, _ = _attempt_one(
                model_id, messages, tree=tree, throttle=throttle, client=client,
            )
        except DailyQuotaExhausted:
            # Primary's path is daily-exhausted: try fallback once if available.
            break

        if result is not None:
            result.retry_count = retry_count
            return result

        last_exc = exc
        retry_count += 1
        if isinstance(exc, DailyQuotaExhausted):
            break  # don't waste another retry on daily exhaustion
        if not is_retryable(exc):
            break  # 4xx / non-transient — retrying just burns quota; go to fallback

    # ── Fallback hop ─────────────────────────────────────────────────────────
    fb_id = FALLBACK_MAP.get(model_id)
    if fb_id is not None:
        try:
            result, exc, _ = _attempt_one(
                fb_id, messages, tree=tree, throttle=throttle, client=client,
            )
            if result is not None:
                result.fallback_triggered = True
                result.retry_count = retry_count
                return result
            last_exc = exc or last_exc
        except DailyQuotaExhausted as exc:
            last_exc = exc

    if isinstance(last_exc, DailyQuotaExhausted):
        raise last_exc
    if last_exc is None:
        last_exc = RuntimeError(f"call_model exhausted without exception on {model_id}")
    raise last_exc


def htb_status() -> dict:
    """Snapshot of HTB tree state — for telemetry, eval_state.json, smoke tests."""
    snap = _HTB.snapshot()
    snap["adaptive"] = {
        "throttled": _THROTTLE._is_throttled,
        "current_root_rate": _HTB.root.rate_per_sec,
        "cooldown_until_monotonic": _THROTTLE.cooldown_until,
    }
    return snap
