"""
evaluator.py
Two public functions used by batch_eval.py and testable standalone.

  run_model(prompt_text, model)         → CallResult
  score_response(prompt_obj, response_text) → dict

Both now route through config.llm.call_model(..., role=...). Empty/unparseable
judge responses produce NaN on ALL FIVE dimensions and set judge_empty=True
(no 0.0 defaults anywhere).

Headline `overall_applicable` is NOT computed here — it lives exclusively in
leaderboard.py to keep one source of truth for headline policy.

Standalone test:
  python evaluator.py                       — eval + judge over SAMPLE_PROMPTS × EVALUATOR_MODELS
                                              (12 API calls; hits real API)
  python evaluator.py --probe-fallbacks     — direct ping to every FALLBACK_MAP value
                                              (1 call per unique fallback model — 4 calls total).
                                              Use this to confirm gemma / nemotron-nano are
                                              actually reachable before a full run, since the
                                              fallback path only fires after MAX_RETRY=2 primary
                                              failures and is otherwise hard to exercise.
"""
import argparse
import json
import sys

from config.llm import (
    EVALUATOR_MODELS,
    EVALUATOR_SYSTEM_PROMPT,
    FALLBACK_MAP,
    JUDGE_MODEL,
    JUDGE_SYSTEM_PROMPT,
    CallResult,
    call_model,
)

# Single source of truth pair: this set mirrors leaderboard.DIMENSIONS. Keep in sync.
EXPECTED_SCORE_KEYS = {"factuality", "reasoning", "instruction_following", "format_compliance", "verbosity"}

# Judge-input truncation. Distinct from batch_eval.STORE_RESPONSE_MAX_CHARS, which
# governs what's persisted to parquet — these two caps are separate decisions and
# must not be conflated (see PLAN-grounded-judging-schema-v2.md).
JUDGE_RESPONSE_MAX_CHARS = 4000   # was hardcoded 1500
JUDGE_PROMPT_MAX_CHARS   = 1500   # was hardcoded 500
GROUND_TRUTH_MAX_CHARS   = 800


def parse_judge_json(raw_text: str) -> tuple[dict[str, float], str | None]:
    """Parse the judge's raw completion into {dim: float|nan}.

    Returns (scores, parse_error). All five EXPECTED_SCORE_KEYS dims are always
    present in the returned dict; null -> NaN. Empty/unparseable input -> all-NaN
    scores + a non-None error string. Used by both production scoring
    (score_response) and the calibration probe runner — keep semantics identical
    between the two callers.
    """
    scores: dict[str, float] = {key: float("nan") for key in EXPECTED_SCORE_KEYS}

    raw_text = (raw_text or "").strip()
    if not raw_text:
        return scores, "Empty judge response"

    # Strip ``` and ```json fences if present.
    raw = raw_text
    if raw.startswith("```"):
        parts = raw.split("```")
        if len(parts) >= 2:
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return scores, f"JSONDecodeError: {exc} | raw={raw[:200]}"

    if not isinstance(parsed, dict):
        return scores, f"Judge returned non-object: {type(parsed).__name__}"

    missing = []
    for key in EXPECTED_SCORE_KEYS:
        if key in parsed:
            val = parsed[key]
            scores[key] = float("nan") if val is None else float(val)
        else:
            missing.append(key)
    parse_error = f"Missing keys: {sorted(missing)}" if missing else None
    return scores, parse_error


def build_judge_user_message(prompt_obj: dict, response_text: str) -> tuple[str, bool]:
    """Build the judge's user-turn content exactly as score_response sends it.

    Returns (message_text, response_truncated). Shared by production scoring
    and second_judge.py so a second judge re-scores the identical input judge 1
    saw — any drift here would make inter-judge disagreement measure prompt
    construction, not judge bias (see PLAN-multi-judge-ensemble.md).
    """
    response_truncated = len(response_text) > JUDGE_RESPONSE_MAX_CHARS
    response_for_judge = response_text[:JUDGE_RESPONSE_MAX_CHARS]

    gt = (prompt_obj.get("ground_truth") or "").strip()
    parts = [f"Prompt: {prompt_obj['prompt_text'][:JUDGE_PROMPT_MAX_CHARS]}"]
    if gt:
        parts.append(f"Reference (ground truth for factuality grounding): {gt[:GROUND_TRUTH_MAX_CHARS]}")
    parts.append(f"Response: {response_for_judge}")
    return "\n\n".join(parts), response_truncated


def run_model(prompt_text: str, model: str) -> CallResult:
    """Send prompt_text to an evaluator model via call_model."""
    messages = [
        {"role": "system", "content": EVALUATOR_SYSTEM_PROMPT},
        {"role": "user",   "content": prompt_text},
    ]
    return call_model(model_id=model, messages=messages, role="evaluator")


def score_response(prompt_obj: dict, response_text: str) -> dict:
    """Send (original prompt + ground truth, if any + model response) to the judge.

    Returns:
        {
            "factuality":            float | nan,
            "reasoning":             float | nan,
            "instruction_following": float | nan,   # NaN on empty/unparseable judge
            "format_compliance":     float | nan,   # NaN on empty/unparseable judge
            "verbosity":             float | nan,   # NaN on empty/unparseable judge
            "judge_latency_ms":      int,
            "judge_tokens_used":     int,
            "judge_model":           str,
            "judge_empty":           bool,
            "fallback_triggered":    bool,
            "retry_count":           int,
            "parse_error":           str | None,
            "gt_provided":           bool,   # ground_truth was non-empty for this prompt
            "response_truncated":    bool,   # response_text exceeded JUDGE_RESPONSE_MAX_CHARS
        }

    Note: headline overall_applicable is computed in leaderboard.py, not here.
    """
    prompt_text, response_truncated = build_judge_user_message(prompt_obj, response_text)
    gt = (prompt_obj.get("ground_truth") or "").strip()

    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user",   "content": prompt_text},
    ]
    result: CallResult = call_model(model_id=JUDGE_MODEL, messages=messages, role="judge")

    scores: dict = {
        "factuality":            float("nan"),
        "reasoning":             float("nan"),
        "instruction_following": float("nan"),
        "format_compliance":     float("nan"),
        "verbosity":             float("nan"),
        "judge_latency_ms":      result.latency_ms,
        "judge_tokens_used":     result.tokens_used,
        "judge_model":           result.model_used,
        "judge_empty":           False,
        "fallback_triggered":    result.fallback_triggered,
        "retry_count":           result.retry_count,
        "parse_error":           None,
        "gt_provided":           bool(gt),
        "response_truncated":    response_truncated,
    }

    parsed_scores, parse_error = parse_judge_json(result.text)
    scores.update(parsed_scores)
    scores["parse_error"] = parse_error
    # judge_empty means "no usable JSON object at all" — missing individual keys
    # still yields a usable (partially-NaN) object, so that case leaves it False.
    hard_failure_prefixes = ("Empty judge response", "JSONDecodeError", "Judge returned non-object")
    if parse_error is not None and parse_error.startswith(hard_failure_prefixes):
        scores["judge_empty"] = True

    return scores


# ── Standalone test ────────────────────────────────────────────────────────────

SAMPLE_PROMPTS = [
    {
        "id": "FR_001",
        "category": "factual_recall",
        "prompt_text": "What is the atomic number of gold?",
        "expected_output_type": "factual_answer",
        "ground_truth": "79",
    },
    {
        "id": "MR_002",
        "category": "multi_step_reasoning",
        "prompt_text": (
            "Alice is three times as old as Bob. "
            "In 8 years, Alice will be twice as old as Bob. "
            "How old is Alice now? Show each algebraic step."
        ),
        "expected_output_type": "reasoning_chain",
        "ground_truth": "24",
    },
]


def probe_fallbacks() -> int:
    """Directly call each unique fallback model with a 1-token prompt.

    Bypasses retry+fallback orchestration so we can confirm the fallback models
    (gemma, nemotron-nano) actually serve responses without first having to
    burn MAX_RETRY=2 primary failures to get there. Returns the number of
    fallback models that failed.
    """
    targets = sorted(set(FALLBACK_MAP.values()))
    print(f"\nProbing {len(targets)} fallback models — one API call each "
          f"(≈{len(targets)} calls total).")
    failed = 0
    for model in targets:
        try:
            result = call_model(
                model_id=model,
                messages=[
                    {"role": "system", "content": "Reply with one word only."},
                    {"role": "user",   "content": "Say 'ok'."},
                ],
                role="evaluator",
            )
            snippet = (result.text or "").strip().replace("\n", " ")[:60]
            tag = " [FALLBACK-HOP]" if result.fallback_triggered else ""
            print(f"  OK   {model}{tag}: {result.latency_ms}ms, "
                  f"{result.tokens_used}t → {snippet!r}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL {model}: {exc}", file=sys.stderr)
    print(f"\n{len(targets) - failed}/{len(targets)} fallback models reachable.")
    return failed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=len(SAMPLE_PROMPTS),
                        help="Number of sample prompts to run (default: all).")
    parser.add_argument("--probe-fallbacks", action="store_true",
                        help="Probe each FALLBACK_MAP value with one direct API call "
                             "(skips the eval+judge loop). Use to verify gemma reachability.")
    args = parser.parse_args()

    if args.probe_fallbacks:
        sys.exit(probe_fallbacks())

    prompts_to_run = SAMPLE_PROMPTS[:args.sample]
    print(f"Evaluator sample run: {len(prompts_to_run)} prompts × "
          f"{len(EVALUATOR_MODELS)} models — WARNING: hits real API "
          f"(~{len(prompts_to_run) * len(EVALUATOR_MODELS) * 2} calls).")
    for model in EVALUATOR_MODELS:
        print(f"\n── Model: {model}")
        for prompt_obj in prompts_to_run:
            try:
                eval_result = run_model(prompt_obj["prompt_text"], model)
                print(f"  {prompt_obj['id']}: {eval_result.latency_ms}ms, "
                      f"{eval_result.tokens_used} tok, "
                      f"fallback={eval_result.fallback_triggered}")
                scores = score_response(prompt_obj, eval_result.text)
                print(f"    scores={scores}")
            except KeyboardInterrupt:
                sys.exit(0)
            except Exception as exc:
                print(f"  [ERROR] {prompt_obj['id']}/{model}: {exc}", file=sys.stderr)
