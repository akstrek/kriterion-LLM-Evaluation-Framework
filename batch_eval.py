"""
batch_eval.py
Resilient sequential eval runner with daily quota awareness.

Architecture:
  - Sequential: one call at a time (methodological purity, single RPM counter)
  - Atomic checkpoint: eval_state.json updated after every call
  - Append-only results: eval_results.parquet written after every scored pair
  - Daily quota detection: graceful exit + Windows Task Scheduler scheduling
  - Exponential backoff: retries for transient errors, skip to failed_calls.json

Run: python batch_eval.py
"""
import datetime
import json
import math
import os
import sys
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

from config.llm import EVALUATOR_MODELS, JUDGE_MODEL, API_CALL_DELAY, DailyQuotaExhausted
from evaluator import run_model, score_response

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR          = "data"
PROMPT_SUITE_PATH = os.path.join("prompts", "prompt_suite.json")
PARQUET_PATH      = os.path.join(DATA_DIR, "eval_results.parquet")
STATE_PATH        = os.path.join(DATA_DIR, "eval_state.json")
FAILED_PATH       = os.path.join(DATA_DIR, "failed_calls.json")
METADATA_PATH     = os.path.join(DATA_DIR, "eval_metadata.json")
FINAL_CSV_PATH    = os.path.join(DATA_DIR, "eval_results.csv")
SCHEDULE_BAT      = "schedule_next_run.bat"

# ── Rate / budget constants ────────────────────────────────────────────────────
DAILY_CALL_BUDGET = 50          # OpenRouter free tier RPD (account-wide)
CALLS_PER_PAIR    = 2           # 1 eval + 1 judge per (prompt, model) pair
PAIRS_PER_DAY     = DAILY_CALL_BUDGET // CALLS_PER_PAIR          # 25
PROMPTS_PER_DAY   = DAILY_CALL_BUDGET // (len(EVALUATOR_MODELS) * CALLS_PER_PAIR)  # 8
MAX_RETRY         = 3

# ── Parquet schema ─────────────────────────────────────────────────────────────
_SCHEMA = pa.schema([
    pa.field("prompt_id",              pa.string()),
    pa.field("model",                  pa.string()),
    pa.field("factuality",             pa.float64()),
    pa.field("reasoning",              pa.float64()),
    pa.field("instruction_following",  pa.float64()),
    pa.field("format_compliance",      pa.float64()),
    pa.field("overall_score",          pa.float64()),
    pa.field("factuality_null",        pa.bool_()),
    pa.field("reasoning_null",         pa.bool_()),
    pa.field("latency_ms",             pa.int64()),
    pa.field("tokens_used",            pa.int64()),
    pa.field("cost_usd",               pa.float64()),
    pa.field("provider",               pa.string()),
    pa.field("is_fallback",            pa.bool_()),
    pa.field("day_of_run",             pa.int32()),
    pa.field("judge_model",            pa.string()),
    pa.field("parse_error",            pa.string()),
    pa.field("judge_latency_ms",       pa.int64()),
    pa.field("judge_tokens_used",      pa.int64()),
])


# ── Utility ────────────────────────────────────────────────────────────────────

def _is_nan(v) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False


def _interruptible_sleep(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        time.sleep(min(0.5, end - time.time()))


# ── State I/O ──────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {
            "total_calls":    0,
            "total_failures": 0,
            "resume_events":  0,
            "day_of_run":     1,
            "started_at":     datetime.datetime.utcnow().isoformat(),
            "last_exhausted": None,
            "next_run_utc":   None,
        }
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_PATH)


# ── Prompt I/O ─────────────────────────────────────────────────────────────────

def load_prompts() -> list[dict]:
    if not os.path.exists(PROMPT_SUITE_PATH):
        sys.exit(f"ERROR: {PROMPT_SUITE_PATH} not found. Run generate_prompts.py first.")
    with open(PROMPT_SUITE_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── Parquet I/O ────────────────────────────────────────────────────────────────

def load_completed_pairs() -> set[tuple[str, str]]:
    if not os.path.exists(PARQUET_PATH):
        return set()
    table = pq.read_table(PARQUET_PATH, columns=["prompt_id", "model"])
    df = table.to_pandas()
    return set(zip(df["prompt_id"], df["model"]))


def append_row_to_parquet(row: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    record = {
        "prompt_id":             str(row["prompt_id"]),
        "model":                 str(row["model"]),
        "factuality":            float("nan") if _is_nan(row["factuality"]) else float(row["factuality"]),
        "reasoning":             float("nan") if _is_nan(row["reasoning"])  else float(row["reasoning"]),
        "instruction_following": float(row["instruction_following"]),
        "format_compliance":     float(row["format_compliance"]),
        "overall_score":         float(row["overall_score"]),
        "factuality_null":       bool(_is_nan(row["factuality"])),
        "reasoning_null":        bool(_is_nan(row["reasoning"])),
        "latency_ms":            int(row["latency_ms"]),
        "tokens_used":           int(row["tokens_used"]),
        "cost_usd":              0.0,
        "provider":              "openrouter",
        "is_fallback":           False,
        "day_of_run":            int(row["day_of_run"]),
        "judge_model":           str(row["judge_model"]),
        "parse_error":           str(row.get("parse_error") or ""),
        "judge_latency_ms":      int(row["judge_latency_ms"]),
        "judge_tokens_used":     int(row["judge_tokens_used"]),
    }
    new_table = pa.Table.from_pydict(
        {k: [v] for k, v in record.items()},
        schema=_SCHEMA,
    )
    if os.path.exists(PARQUET_PATH):
        existing = pq.read_table(PARQUET_PATH)
        new_table = pa.concat_tables([existing, new_table])

    tmp = PARQUET_PATH + ".tmp"
    pq.write_table(new_table, tmp)
    with open(tmp, "r+b") as f:
        os.fsync(f.fileno())
    os.replace(tmp, PARQUET_PATH)


# ── Failed calls log ───────────────────────────────────────────────────────────

def load_failed_calls() -> list[dict]:
    if not os.path.exists(FAILED_PATH):
        return []
    with open(FAILED_PATH, encoding="utf-8") as f:
        return json.load(f)


def append_failed_call(entry: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    failed = load_failed_calls()
    failed.append(entry)
    tmp = FAILED_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(failed, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, FAILED_PATH)


# ── Metadata ───────────────────────────────────────────────────────────────────

def save_metadata(state: dict, completed: int, total: int) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    meta = {
        "total_days":      state["day_of_run"],
        "total_calls":     state["total_calls"],
        "total_failures":  state["total_failures"],
        "provider":        "openrouter",
        "cost_usd":        0.00,
        "resume_events":   state["resume_events"],
        "completed_pairs": completed,
        "total_pairs":     total,
        "completed_at":    datetime.datetime.utcnow().isoformat(),
    }
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


# ── Daily quota handling ───────────────────────────────────────────────────────

def log_exhaustion_and_schedule_next_run(state: dict) -> None:
    reset_utc = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).replace(
        hour=0, minute=1, second=0, microsecond=0
    )
    state["last_exhausted"] = datetime.datetime.utcnow().isoformat()
    state["next_run_utc"]   = reset_utc.isoformat()
    state["day_of_run"]    += 1
    save_state(state)

    reset_local = reset_utc.replace(tzinfo=datetime.timezone.utc).astimezone(tz=None)
    reset_time = reset_local.strftime("%H:%M")
    bat = (
        f'schtasks /create /tn "KriterionEval" '
        f'/tr "python batch_eval.py" /sc once /st {reset_time} /f\n'
    )
    with open(SCHEDULE_BAT, "w") as f:
        f.write(bat)

    print(f"\nDaily quota exhausted ({DAILY_CALL_BUDGET} calls used).")
    print(f"Run schedule_next_run.bat to auto-resume at {reset_time} UTC.")
    print(f"Or re-run manually after {reset_utc.strftime('%Y-%m-%d %H:%M')} UTC.")


# ── Row builder ────────────────────────────────────────────────────────────────

def build_result_row(
    prompt_obj: dict,
    model: str,
    eval_result: dict,
    scores: dict,
    day_of_run: int,
) -> dict:
    return {
        "prompt_id":             prompt_obj["id"],
        "model":                 model,
        "factuality":            scores["factuality"],
        "reasoning":             scores["reasoning"],
        "instruction_following": scores["instruction_following"],
        "format_compliance":     scores["format_compliance"],
        "overall_score":         scores["overall_score"],
        "latency_ms":            eval_result["latency_ms"],
        "tokens_used":           eval_result["tokens_used"],
        "judge_model":           JUDGE_MODEL,
        "parse_error":           scores.get("parse_error") or "",
        "judge_latency_ms":      scores["judge_latency_ms"],
        "judge_tokens_used":     scores["judge_tokens_used"],
        "day_of_run":            day_of_run,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)

    prompts         = load_prompts()
    state           = load_state()
    completed_pairs = load_completed_pairs()

    n_models    = len(EVALUATOR_MODELS)
    total_pairs = len(prompts) * n_models
    todo_pairs  = [
        (p, m)
        for p in prompts
        for m in EVALUATOR_MODELS
        if (p["id"], m) not in completed_pairs
    ]
    days_remaining = math.ceil(len(todo_pairs) / PAIRS_PER_DAY) if todo_pairs else 0

    # ── Banner ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("Kriterion Batch Evaluation  —  Sequential Daily Runner")
    print("=" * 70)
    print(f"  Prompts:            {len(prompts)}")
    print(f"  Models:             {n_models}  (sequential)")
    print(f"  Total pairs:        {total_pairs}")
    print(f"  Completed:          {len(completed_pairs)}")
    print(f"  Remaining pairs:    {len(todo_pairs)}")
    print(f"  Daily budget:       {DAILY_CALL_BUDGET} calls  →  {PAIRS_PER_DAY} pairs/day  ({PROMPTS_PER_DAY} full prompts/day)")
    print(f"  Est. days left:     ~{days_remaining}")
    print(f"  Day of run:         {state['day_of_run']}")
    print(f"  Total calls so far: {state['total_calls']}")
    print(f"  Failures logged:    {state['total_failures']}")
    print(f"  Resume events:      {state['resume_events']}")
    print(f"  Inter-call delay:   {API_CALL_DELAY}s")
    print(f"  Checkpoint:         {STATE_PATH}")
    print(f"  Results:            {PARQUET_PATH}")
    print()

    if not todo_pairs:
        print("Nothing to run — all pairs completed.")
        if os.path.exists(PARQUET_PATH):
            pq.read_table(PARQUET_PATH).to_pandas().to_csv(FINAL_CSV_PATH, index=False)
            print(f"Final CSV written: {FINAL_CSV_PATH}")
        save_metadata(state, len(completed_pairs), total_pairs)
        _print_completion_summary(state)
        return

    if len(completed_pairs) > 0:
        state["resume_events"] += 1
        save_state(state)

    confirm = input("Proceed? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    # ── Main loop ─────────────────────────────────────────────────────────────
    try:
        with tqdm(total=len(todo_pairs), unit="pair", desc="Evaluating") as pbar:
            for prompt_obj, model in todo_pairs:
                pid = prompt_obj["id"]

                # ── Evaluator call ────────────────────────────────────────────
                # Recover a checkpointed eval result if quota hit mid-judge on the prior run
                pending = state.get("pending_eval")
                if pending and pending["prompt_id"] == pid and pending["model"] == model:
                    eval_result = pending
                else:
                    eval_result = None
                    state.pop("pending_eval", None)

                if eval_result is None:
                    for attempt in range(MAX_RETRY + 1):
                        try:
                            eval_result = run_model(prompt_obj["prompt_text"], model)
                            state["total_calls"] += 1
                            save_state(state)
                            break
                        except DailyQuotaExhausted:
                            log_exhaustion_and_schedule_next_run(state)
                            sys.exit(0)
                        except KeyboardInterrupt:
                            raise
                        except Exception as exc:
                            wait = 30 * (attempt + 1)
                            tqdm.write(
                                f"[EVAL {attempt+1}/{MAX_RETRY}] {pid}/{model}: {exc}"
                                + (f"  — retry in {wait}s" if attempt < MAX_RETRY else "  — skipping")
                            )
                            if attempt < MAX_RETRY:
                                _interruptible_sleep(wait)
                            else:
                                append_failed_call({
                                    "prompt_id": pid, "model": model, "stage": "eval",
                                    "error": str(exc),
                                    "timestamp": datetime.datetime.utcnow().isoformat(),
                                })
                                state["total_failures"] += 1
                                save_state(state)

                if eval_result is None:
                    pbar.update(1)
                    continue

                # Checkpoint eval result so a quota hit during judge doesn't waste the eval call
                state["pending_eval"] = {
                    "prompt_id": pid, "model": model,
                    "text": eval_result["text"],
                    "latency_ms": eval_result["latency_ms"],
                    "tokens_used": eval_result["tokens_used"],
                }
                save_state(state)

                # ── Judge call ────────────────────────────────────────────────
                scores = None
                for attempt in range(MAX_RETRY + 1):
                    try:
                        scores = score_response(prompt_obj, eval_result["text"])
                        state["total_calls"] += 1
                        save_state(state)
                        break
                    except DailyQuotaExhausted:
                        log_exhaustion_and_schedule_next_run(state)
                        sys.exit(0)
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        wait = 30 * (attempt + 1)
                        tqdm.write(
                            f"[JUDGE {attempt+1}/{MAX_RETRY}] {pid}/{model}: {exc}"
                            + (f"  — retry in {wait}s" if attempt < MAX_RETRY else "  — skipping")
                        )
                        if attempt < MAX_RETRY:
                            _interruptible_sleep(wait)
                        else:
                            append_failed_call({
                                "prompt_id": pid, "model": model, "stage": "judge",
                                "error": str(exc),
                                "eval_latency_ms": eval_result["latency_ms"],
                                "timestamp": datetime.datetime.utcnow().isoformat(),
                            })
                            state["total_failures"] += 1
                            save_state(state)

                if scores is None:
                    pbar.update(1)
                    continue

                # ── Persist ───────────────────────────────────────────────────
                row = build_result_row(prompt_obj, model, eval_result, scores, state["day_of_run"])
                append_row_to_parquet(row)
                state.pop("pending_eval", None)
                save_state(state)
                pbar.update(1)

        # ── Completion ────────────────────────────────────────────────────────
        final_set = load_completed_pairs()
        final_completed = len(completed_pairs) + sum(
            1 for p, m in todo_pairs
            if (p["id"], m) in final_set
        )
        if os.path.exists(PARQUET_PATH):
            pq.read_table(PARQUET_PATH).to_pandas().to_csv(FINAL_CSV_PATH, index=False)

        save_metadata(state, final_completed, total_pairs)
        _print_completion_summary(state)

    except KeyboardInterrupt:
        print("\nInterrupted — state saved.", flush=True)
        sys.exit(0)


def _print_completion_summary(state: dict) -> None:
    print("\n── Run summary ──────────────────────────────────────────────────────")
    print(f"  Total calls:    {state['total_calls']}")
    print(f"  Failures:       {state['total_failures']}")
    print(f"  Days of run:    {state['day_of_run']}")
    print(f"  Provider:       openrouter")
    print(f"  Cost:           $0.00 (free tier)")
    print(f"  Resume events:  {state['resume_events']}")
    if os.path.exists(FINAL_CSV_PATH):
        print(f"  CSV output:     {FINAL_CSV_PATH}")
    if os.path.exists(METADATA_PATH):
        print(f"  Metadata:       {METADATA_PATH}")


if __name__ == "__main__":
    main()
