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


def run_model(prompt_text: str, model: str) -> CallResult:
    """Send prompt_text to an evaluator model via call_model."""
    messages = [
        {"role": "system", "content": EVALUATOR_SYSTEM_PROMPT},
        {"role": "user",   "content": prompt_text},
    ]
    return call_model(model_id=model, messages=messages, role="evaluator")


def score_response(prompt_obj: dict, response_text: str) -> dict:
    """Send (original prompt + model response) to the judge.

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
        }

    Note: headline overall_applicable is computed in leaderboard.py, not here.
    """
    response_truncated = response_text[:1500]
    prompt_text = f"Prompt: {prompt_obj['prompt_text'][:500]}\n\nResponse: {response_truncated}"

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
    }

    raw_text = (result.text or "").strip()
    if not raw_text:
        scores["judge_empty"] = True
        scores["parse_error"] = "Empty judge response"
        return scores

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
        scores["judge_empty"] = True
        scores["parse_error"] = f"JSONDecodeError: {exc} | raw={raw[:200]}"
        return scores

    if not isinstance(parsed, dict):
        scores["judge_empty"] = True
        scores["parse_error"] = f"Judge returned non-object: {type(parsed).__name__}"
        return scores

    missing = []
    for key in EXPECTED_SCORE_KEYS:
        if key in parsed:
            val = parsed[key]
            scores[key] = float("nan") if val is None else float(val)
        else:
            missing.append(key)
    if missing:
        scores["parse_error"] = f"Missing keys: {sorted(missing)}"

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
