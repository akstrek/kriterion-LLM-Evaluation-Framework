"""
evaluator.py
Two public functions used by batch_eval.py and testable standalone.

  run_model(prompt_text, model)  → dict   {"text", "latency_ms", "tokens_used", "cost_usd"}
  score_response(prompt_obj, response_text) → dict

Standalone test:
  python evaluator.py            — runs all 3 prompts × all evaluator models
  python evaluator.py --sample 2 — runs first 2 prompts × all evaluator models
"""
import argparse
import json
import sys

import numpy as np

from config.llm import (
    EVALUATOR_MODELS,
    EVALUATOR_SYSTEM_PROMPT,
    JUDGE_MODEL,
    JUDGE_SYSTEM_PROMPT,
    get_llm_response,
)

EXPECTED_SCORE_KEYS = {"factuality", "reasoning", "instruction_following", "format_compliance"}


def run_model(prompt_text: str, model: str) -> dict:
    """
    Send prompt_text to an evaluator model.

    Returns the full result dict from get_llm_response:
        {"text", "latency_ms", "tokens_used", "cost_usd"}
    """
    return get_llm_response(
        prompt=prompt_text,
        system=EVALUATOR_SYSTEM_PROMPT,
        model=model,
    )


def score_response(prompt_obj: dict, response_text: str) -> dict:
    """
    Send (original prompt + model response) to the NVIDIA: Nemotron 3 Super judge.
    Both are truncated before sending: response capped at 1500 chars (~375 tokens),
    prompt_text capped at 500 chars.

    prompt_obj must have at least: {"prompt_text": str}

    Returns:
        {
            "factuality":            float | nan,   # nan when not applicable
            "reasoning":             float | nan,   # nan when not applicable
            "instruction_following": float,
            "format_compliance":     float,
            "overall_score":         float,         # nanmean of non-null dims
            "judge_latency_ms":      int,
            "judge_tokens_used":     int,
            "parse_error":           str | None,
        }
    """
    response_truncated = response_text[:1500]
    prompt_text = f"Prompt: {prompt_obj['prompt_text'][:500]}\n\nResponse: {response_truncated}"

    judge_prompt = prompt_text

    result = get_llm_response(
        prompt=judge_prompt,
        system=JUDGE_SYSTEM_PROMPT,
        model=JUDGE_MODEL,
    )

    scores = {
        "factuality":            float("nan"),  # nullable per judge schema
        "reasoning":             float("nan"),  # nullable per judge schema
        "instruction_following": 0.0,
        "format_compliance":     0.0,
        "overall_score":         float("nan"),
        "judge_latency_ms":      result["latency_ms"],
        "judge_tokens_used":     result["tokens_used"],
        "parse_error":           None,
    }

    if not result["text"].strip():
        print(f"  [WARN] Judge returned empty response for prompt {prompt_obj.get('id', '?')}")
        scores["parse_error"] = "Empty judge response"
        return scores

    raw = result["text"].strip()
    # Strip markdown fences if the judge wraps them anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
        for key in EXPECTED_SCORE_KEYS:
            if key in parsed:
                val = parsed[key]
                scores[key] = float("nan") if val is None else float(val)
            else:
                scores["parse_error"] = f"Missing key: {key}"
    except json.JSONDecodeError as exc:
        scores["parse_error"] = f"JSONDecodeError: {exc} | raw={raw[:200]}"

    # overall_score excludes null (nan) dimensions
    scores["overall_score"] = float(np.nanmean([
        scores["factuality"],
        scores["reasoning"],
        scores["instruction_following"],
        scores["format_compliance"],
    ]))

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
    {
        "id": "IF_014",
        "category": "instruction_following",
        "prompt_text": (
            "Create a JSON object representing a person. "
            "Constraints: (1) Valid, parseable JSON. "
            "(2) Exactly 5 fields: name, age, occupation, city, hobbies. "
            "(3) 'hobbies' must be an array of exactly 3 items. "
            "(4) Double quotes for all strings. "
            "(5) Output JSON only — no explanation."
        ),
        "expected_output_type": "constrained_text",
        "ground_truth": None,
    },
]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=len(SAMPLE_PROMPTS),
                        help="Number of sample prompts to run (default: all)")
    args = parser.parse_args()

    prompts_to_run = SAMPLE_PROMPTS[:args.sample]

    print("=" * 70)
    print(f"Evaluator sample run: {len(prompts_to_run)} prompts × {len(EVALUATOR_MODELS)} models")
    print("Rate limiting is handled automatically in config/llm.py")
    print("=" * 70)

    for model in EVALUATOR_MODELS:
        print(f"\n── Model: {model}")
        for prompt_obj in prompts_to_run:
            pid = prompt_obj["id"]
            print(f"\n  Prompt {pid}: {prompt_obj['prompt_text'][:60]}...")

            try:
                eval_result = run_model(prompt_obj["prompt_text"], model)
                response_text = eval_result["text"]
                print(f"  Response ({eval_result['latency_ms']} ms, {eval_result['tokens_used']} tokens):")
                print(f"    {response_text[:120].replace(chr(10), ' ')}")

                scores = score_response(prompt_obj, response_text)
                if scores["parse_error"]:
                    print(f"  [Judge parse error]: {scores['parse_error']}")
                else:
                    fact_str = f"{scores['factuality']:.2f}" if not (scores['factuality'] != scores['factuality']) else "null"
                    reas_str = f"{scores['reasoning']:.2f}" if not (scores['reasoning'] != scores['reasoning']) else "null"
                    print(
                        f"  Scores → factuality={fact_str}  "
                        f"reasoning={reas_str}  "
                        f"instr_following={scores['instruction_following']:.2f}  "
                        f"format={scores['format_compliance']:.2f}  "
                        f"overall={scores['overall_score']:.2f}  "
                        f"(judge {scores['judge_latency_ms']} ms)"
                    )
            except KeyboardInterrupt:
                print("\nInterrupted.", file=sys.stderr)
                sys.exit(0)
            except Exception as exc:
                print(f"  [ERROR]: {exc}", file=sys.stderr)

    print("\nDone.")
