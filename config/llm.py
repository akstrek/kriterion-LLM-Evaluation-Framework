"""
config/llm.py
Single entry point for all LLM calls via OpenRouter (OpenAI-compatible SDK).
All evaluator calls and judge calls route through get_llm_response().

Per-provider rate limiting is enforced here so callers need no sleep logic.
Concurrent calls to different providers proceed in parallel; calls to the
same provider are serialized with a minimum API_CALL_DELAY between them.
"""
import collections
import os
import threading
import time

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

load_dotenv()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise EnvironmentError(
        "OPENROUTER_API_KEY is not set. "
        "Create a .env file with: OPENROUTER_API_KEY=your_key_here"
    )

JUDGE_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

EVALUATOR_MODELS = [
    "minimax/minimax-m2.5:free",
    "openai/gpt-oss-20b:free",
    "openai/gpt-oss-120b:free",
]


def _assert_free_only(models: list[str]) -> None:
    """Hard-fail if any model ID does not end in ':free' — prevents credit burn."""
    bad = [m for m in models if not m.endswith(":free")]
    if bad:
        raise ValueError(
            f"Non-:free model IDs are forbidden to prevent credit burn: {bad}. "
            "All evaluator/judge models must end in ':free'."
        )


_assert_free_only(EVALUATOR_MODELS + [JUDGE_MODEL])

API_CALL_DELAY = 4.0  # legacy per-provider min gap (still enforced)

# Global 20-RPM ceiling (OpenRouter :free hard limit). 18/min leaves 10% headroom.
GLOBAL_RPM_LIMIT = 18
_RPM_WINDOW_SECONDS = 60.0
_rpm_lock = threading.Lock()
_rpm_timestamps: "collections.deque[float]" = collections.deque()


def _wait_for_global_rpm() -> None:
    """Block until a 20-RPM token is available (sliding 60s window)."""
    while True:
        with _rpm_lock:
            now = time.time()
            while _rpm_timestamps and now - _rpm_timestamps[0] >= _RPM_WINDOW_SECONDS:
                _rpm_timestamps.popleft()
            if len(_rpm_timestamps) < GLOBAL_RPM_LIMIT:
                _rpm_timestamps.append(now)
                return
            sleep_for = _RPM_WINDOW_SECONDS - (now - _rpm_timestamps[0]) + 0.05
        _interruptible_sleep(max(0.1, sleep_for))

JUDGE_SYSTEM_PROMPT = """Score this prompt-response pair. Use full 0.00-1.00 range — most responses score 0.40-0.85, not 1.00.
factuality: claim accuracy. 1.00=every claim verifiable. 0.85=minor imprecision. 0.60=one wrong claim. 0.30=multiple errors. 0.00=fabricated. null if no factual claims.
reasoning: inferential validity AND depth. 1.00=correct + insightful. 0.85=correct but shallow. 0.60=mostly correct, one weak step. 0.30=flawed logic. 0.00=incoherent. null if no reasoning required.
instruction_following: constraint satisfaction. Count explicit constraints (length, format, scope, exclusions). Score = constraints_met / constraints_total. Partial credit per constraint. Score implied intent if none explicit.
format_compliance: structural exactness. 1.00=perfect structure. 0.85=correct structure, minor deviation. 0.60=right format, wrong details. 0.30=wrong format. 0.00=no structure attempted.
Penalize: hedging, padding, unnecessary preamble, repetition. Reward: precision, completeness within minimal tokens.
Return JSON only: {"factuality":0.00,"reasoning":0.00,"instruction_following":0.00,"format_compliance":0.00}
null example: {"factuality":null,"reasoning":null,"instruction_following":0.85,"format_compliance":0.92}"""

EVALUATOR_SYSTEM_PROMPT = (
    "You are a helpful, precise AI assistant. Answer the user's prompt directly.\n"
    "Be concise. Be accurate. Follow all formatting instructions exactly.\n"
    "If the prompt asks for a specific format (JSON, list, code), use that format only.\n"
    "Do not add disclaimers, caveats, or meta-commentary about your response."
)

_client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

# ── Per-provider rate limiting ────────────────────────────────────────────────
_registry_lock:   threading.Lock             = threading.Lock()
_provider_locks:  dict[str, threading.Lock]  = {}
_last_call_time:  dict[str, float]           = {}

_RETRY_DELAYS = [10, 30, 60, 120]


def _get_provider(model_id: str) -> str:
    return model_id.split("/")[0]


def _interruptible_sleep(seconds: float) -> None:
    """Sleep in 0.5 s chunks so KeyboardInterrupt fires promptly."""
    end = time.time() + seconds
    while time.time() < end:
        time.sleep(min(0.5, end - time.time()))


def _wait_for_provider(provider: str) -> None:
    """
    Ensure at least API_CALL_DELAY seconds between consecutive calls to the
    same provider. Calls to different providers proceed without blocking.
    """
    with _registry_lock:
        if provider not in _provider_locks:
            _provider_locks[provider] = threading.Lock()
            _last_call_time[provider] = 0.0

    with _provider_locks[provider]:
        elapsed = time.time() - _last_call_time[provider]
        if elapsed < API_CALL_DELAY:
            _interruptible_sleep(API_CALL_DELAY - elapsed)
        _last_call_time[provider] = time.time()


class DailyQuotaExhausted(Exception):
    """Raised when OpenRouter free daily quota is exhausted."""
    pass

# ── Public call function ──────────────────────────────────────────────────────

def get_llm_response(prompt: str, system: str, model: str) -> dict:
    """
    Send a prompt to any model via OpenRouter.

    - Enforces per-provider rate limiting before every attempt.
    - Retries up to 4 times on 429 with exponential back-off.
    - Uses interruptible sleeps so Ctrl-C is caught within 0.5 s.

    Returns:
        {
            "text":        str,
            "latency_ms":  int,
            "tokens_used": int,
            "cost_usd":    float,   # 0.0 for :free tier models
        }

    Raises:
        KeyboardInterrupt — propagated immediately from any sleep.
        RateLimitError    — if all retry attempts are exhausted.
        Exception         — any other OpenAI/network error.
    """
    provider = _get_provider(model)
    last_exc: Exception | None = None

    for attempt, retry_wait in enumerate([0] + _RETRY_DELAYS):
        if retry_wait:
            print(
                f"  [429] {model} — waiting {retry_wait}s "
                f"before retry {attempt}/{len(_RETRY_DELAYS)} ...",
                flush=True,
            )
            _interruptible_sleep(retry_wait)

        _wait_for_provider(provider)
        _wait_for_global_rpm()

        try:
            start = time.time()
            response = _client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.0,
                extra_body={"provider": {"allow_fallbacks": False}},
            )
            latency_ms  = int((time.time() - start) * 1000)
            if not response.choices:
                last_exc = ValueError(f"Empty choices in response from {model}")
                continue
            text        = response.choices[0].message.content or ""
            usage       = response.usage
            tokens_used = usage.total_tokens if usage else 0

            return {
                "text":        text,
                "latency_ms":  latency_ms,
                "tokens_used": tokens_used,
                "cost_usd":    0.0,
            }

        except RateLimitError as exc:
            if "free-models-per-day" in str(exc).lower():
                raise DailyQuotaExhausted(str(exc))
            last_exc = exc
            continue

    # All retries failed on RateLimitError — quota is exhausted regardless of message format
    if isinstance(last_exc, RateLimitError):
        raise DailyQuotaExhausted(f"All retries exhausted on RateLimitError: {last_exc}")
    raise last_exc  # type: ignore[misc]
