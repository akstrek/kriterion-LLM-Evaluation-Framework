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
import argparse
import datetime
import json
import math
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timezone

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

from config.llm import (
    API_CALL_DELAY,
    DailyQuotaExhausted,
    EVALUATOR_MODELS,
    JUDGE_MODEL,
    OPENROUTER_API_KEY,
)
from evaluator import run_model, score_response

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR          = "data"
ROWS_DIR          = os.path.join(DATA_DIR, "rows")
PROMPT_SUITE_PATH = os.path.join("prompts", "prompt_suite.json")
PARQUET_PATH      = os.path.join(DATA_DIR, "eval_results.parquet")
STATE_PATH        = os.path.join(DATA_DIR, "eval_state.json")
FAILED_PATH       = os.path.join(DATA_DIR, "failed_calls.json")
METADATA_PATH     = os.path.join(DATA_DIR, "eval_metadata.json")
FINAL_CSV_PATH    = os.path.join(DATA_DIR, "eval_results.csv")
SCHEDULE_BAT      = "schedule_next_run.bat"

# ── Rate / budget constants ────────────────────────────────────────────────────
# With >=10 OpenRouter credits, :free RPD = 1000. Leave a 50-call safety buffer.
DAILY_CALL_BUDGET = 950
CALLS_PER_PAIR    = 2           # 1 eval + 1 judge per (prompt, model) pair
PAIRS_PER_DAY     = DAILY_CALL_BUDGET // CALLS_PER_PAIR
PROMPTS_PER_DAY   = DAILY_CALL_BUDGET // (len(EVALUATOR_MODELS) * CALLS_PER_PAIR)
MAX_RETRY         = 3
# Per-prompt fan-out: run all evaluator models (and then all judges) concurrently.
# Global 20-RPM token bucket in config/llm.py keeps the OpenRouter ceiling safe.
PROMPT_WORKERS    = len(EVALUATOR_MODELS)

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
            "started_at":     datetime.datetime.now(timezone.utc).isoformat(),
            "last_exhausted": None,
            "next_run_utc":   None,
        }
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    import time
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    for attempt in range(5):
        try:
            os.replace(tmp, STATE_PATH)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))


# ── Prompt I/O ─────────────────────────────────────────────────────────────────

def load_prompts() -> list[dict]:
    if not os.path.exists(PROMPT_SUITE_PATH):
        sys.exit(f"ERROR: {PROMPT_SUITE_PATH} not found. Run generate_prompts.py first.")
    with open(PROMPT_SUITE_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── Parquet I/O ────────────────────────────────────────────────────────────────

def _safe_model_filename(model: str) -> str:
    return model.replace("/", "__").replace(":", "_")


def _row_path(prompt_id: str, model: str) -> str:
    return os.path.join(ROWS_DIR, f"{prompt_id}__{_safe_model_filename(model)}.parquet")


def _read_legacy_pairs() -> set[tuple[str, str]]:
    if not os.path.exists(PARQUET_PATH):
        return set()
    table = pq.read_table(PARQUET_PATH, columns=["prompt_id", "model"])
    df = table.to_pandas()
    return set(zip(df["prompt_id"], df["model"]))


def load_completed_pairs() -> set[tuple[str, str]]:
    """Union of legacy single-file parquet and the per-row directory.
    Reads each row file's prompt_id+model columns directly (filename is opaque)."""
    pairs = _read_legacy_pairs()
    if os.path.isdir(ROWS_DIR):
        for fname in os.listdir(ROWS_DIR):
            if not fname.endswith(".parquet"):
                continue
            try:
                t = pq.read_table(
                    os.path.join(ROWS_DIR, fname),
                    columns=["prompt_id", "model"],
                )
                if t.num_rows:
                    pairs.add((str(t["prompt_id"][0].as_py()),
                               str(t["model"][0].as_py())))
            except Exception:
                continue
    return pairs


def append_row_to_parquet(row: dict) -> None:
    """O(1) per-row write — one parquet file per (prompt_id, model)."""
    os.makedirs(ROWS_DIR, exist_ok=True)
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
    table = pa.Table.from_pydict(
        {k: [v] for k, v in record.items()},
        schema=_SCHEMA,
    )
    final_path = _row_path(record["prompt_id"], record["model"])
    tmp = final_path + ".tmp"
    pq.write_table(table, tmp)
    with open(tmp, "r+b") as f:
        os.fsync(f.fileno())
    os.replace(tmp, final_path)


def consolidate_rows_to_parquet() -> int:
    """Concatenate all per-row parquet files (plus legacy file) into PARQUET_PATH.
    Returns the total row count written."""
    tables = []
    if os.path.exists(PARQUET_PATH):
        tables.append(pq.read_table(PARQUET_PATH))
    if os.path.isdir(ROWS_DIR):
        for fname in sorted(os.listdir(ROWS_DIR)):
            if fname.endswith(".parquet"):
                tables.append(pq.read_table(os.path.join(ROWS_DIR, fname)))
    if not tables:
        return 0
    combined = pa.concat_tables(tables, promote_options="default")
    tmp = PARQUET_PATH + ".tmp"
    pq.write_table(combined, tmp)
    with open(tmp, "r+b") as f:
        os.fsync(f.fileno())
    os.replace(tmp, PARQUET_PATH)
    return combined.num_rows


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
        "completed_at":    datetime.datetime.now(timezone.utc).isoformat(),
    }
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


# ── Credit check ───────────────────────────────────────────────────────────────

def fetch_key_info() -> dict | None:
    """GET https://openrouter.ai/api/v1/key — returns the `data` payload or None."""
    if not OPENROUTER_API_KEY:
        return None
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/key",
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return payload.get("data")
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        print(f"  (credit check failed: {exc})")
        return None


def print_credit_status(label: str, info: dict | None) -> None:
    if not info:
        print(f"  {label}: <unavailable>")
        return
    usage = info.get("usage")
    limit = info.get("limit")
    remaining = (limit - usage) if (limit is not None and usage is not None) else None
    rate = info.get("rate_limit") or {}
    print(f"  {label}:")
    print(f"    usage:     ${usage:.4f}" if usage is not None else "    usage:     <n/a>")
    print(f"    limit:     ${limit:.4f}" if limit is not None else "    limit:     <unlimited>")
    if remaining is not None:
        print(f"    remaining: ${remaining:.4f}")
    if rate:
        print(f"    rate_limit:{rate.get('requests')} / {rate.get('interval')}")


# ── Daily quota handling ───────────────────────────────────────────────────────

def log_exhaustion_and_schedule_next_run(state: dict) -> None:
    reset_utc = (datetime.datetime.now(timezone.utc) + datetime.timedelta(days=1)).replace(
        hour=0, minute=1, second=0, microsecond=0
    )
    state["last_exhausted"] = datetime.datetime.now(timezone.utc).isoformat()
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


# ── Per-pair processor (thread-safe) ──────────────────────────────────────────

_STATE_LOCK = threading.Lock()


def _pending_key(pid: str, model: str) -> str:
    return f"{pid}|{model}"


def _migrate_legacy_pending(state: dict) -> None:
    """Convert legacy single 'pending_eval' to keyed 'pending_evals' dict."""
    if "pending_eval" in state and state["pending_eval"]:
        pe = state.pop("pending_eval")
        state.setdefault("pending_evals", {})[_pending_key(pe["prompt_id"], pe["model"])] = pe
    elif "pending_eval" in state:
        state.pop("pending_eval", None)
    state.setdefault("pending_evals", {})


class _QuotaSignal(Exception):
    """Internal signal to break out of the executor on DailyQuotaExhausted."""


def process_pair(prompt_obj: dict, model: str, state: dict) -> None:
    """Run one (prompt, model) pair end-to-end. Thread-safe via _STATE_LOCK
    for state mutations. Raises _QuotaSignal on DailyQuotaExhausted."""
    pid = prompt_obj["id"]
    key = _pending_key(pid, model)

    # Recover checkpointed eval if quota hit mid-judge on a prior run
    with _STATE_LOCK:
        pending = state.get("pending_evals", {}).get(key)
    eval_result = pending if pending else None

    # ── Evaluator ─────────────────────────────────────────────────────────────
    if eval_result is None:
        total_attempts = MAX_RETRY + 1
        for attempt in range(total_attempts):
            with _STATE_LOCK:
                state["total_calls"] += 1
                save_state(state)
            try:
                eval_result = run_model(prompt_obj["prompt_text"], model)
                break
            except DailyQuotaExhausted:
                raise _QuotaSignal()
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                wait = 30 * (attempt + 1)
                is_last = attempt == total_attempts - 1
                tqdm.write(
                    f"[EVAL {attempt+1}/{total_attempts}] {pid}/{model}: {exc}"
                    + ("  — skipping" if is_last else f"  — retry in {wait}s")
                )
                if not is_last:
                    _interruptible_sleep(wait)
                else:
                    append_failed_call({
                        "prompt_id": pid, "model": model, "stage": "eval",
                        "error": str(exc),
                        "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
                    })
                    with _STATE_LOCK:
                        state["total_failures"] += 1
                        save_state(state)
                    return

    if eval_result is None:
        return

    # Checkpoint eval result so a quota hit during judge doesn't waste the eval call
    with _STATE_LOCK:
        state.setdefault("pending_evals", {})[key] = {
            "prompt_id": pid, "model": model,
            "text": eval_result["text"],
            "latency_ms": eval_result["latency_ms"],
            "tokens_used": eval_result["tokens_used"],
        }
        save_state(state)

    # ── Judge ─────────────────────────────────────────────────────────────────
    scores = None
    total_attempts = MAX_RETRY + 1
    for attempt in range(total_attempts):
        with _STATE_LOCK:
            state["total_calls"] += 1
            save_state(state)
        try:
            scores = score_response(prompt_obj, eval_result["text"])
            break
        except DailyQuotaExhausted:
            raise _QuotaSignal()
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            wait = 30 * (attempt + 1)
            is_last = attempt == total_attempts - 1
            tqdm.write(
                f"[JUDGE {attempt+1}/{total_attempts}] {pid}/{model}: {exc}"
                + ("  — skipping" if is_last else f"  — retry in {wait}s")
            )
            if not is_last:
                _interruptible_sleep(wait)
            else:
                append_failed_call({
                    "prompt_id": pid, "model": model, "stage": "judge",
                    "error": str(exc),
                    "eval_latency_ms": eval_result["latency_ms"],
                    "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
                })
                with _STATE_LOCK:
                    state["total_failures"] += 1
                    save_state(state)
                return

    if scores is None:
        return

    # ── Persist ───────────────────────────────────────────────────────────────
    with _STATE_LOCK:
        day_of_run = state["day_of_run"]
    row = build_result_row(prompt_obj, model, eval_result, scores, day_of_run)
    append_row_to_parquet(row)
    with _STATE_LOCK:
        state.get("pending_evals", {}).pop(key, None)
        save_state(state)


# ── Main ──────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kriterion sequential eval runner")
    p.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip the interactive confirmation (required for Task Scheduler runs).",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    os.makedirs(DATA_DIR, exist_ok=True)

    prompts         = load_prompts()
    state           = load_state()
    completed_pairs = load_completed_pairs()

    # ── Pre-flight credit check ───────────────────────────────────────────────
    key_info_start = fetch_key_info()
    if key_info_start is not None and "credits_at_start" not in state:
        state["credits_at_start"] = {
            "usage": key_info_start.get("usage"),
            "limit": key_info_start.get("limit"),
            "checked_at": datetime.datetime.now(timezone.utc).isoformat(),
        }
        save_state(state)

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
    print("Kriterion Batch Evaluation  —  Concurrent Daily Runner")
    print("=" * 70)
    print(f"  Prompts:            {len(prompts)}")
    print(f"  Models:             {n_models}  (concurrent, {PROMPT_WORKERS} workers)")
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
    print_credit_status("Credits (pre-flight)", key_info_start)
    print()

    if not todo_pairs:
        print("Nothing to run — all pairs completed.")
        consolidate_rows_to_parquet()
        if os.path.exists(PARQUET_PATH):
            pq.read_table(PARQUET_PATH).to_pandas().to_csv(FINAL_CSV_PATH, index=False)
            print(f"Final CSV written: {FINAL_CSV_PATH}")
        save_metadata(state, len(completed_pairs), total_pairs)
        _print_completion_summary(state)
        return

    if len(completed_pairs) > 0:
        state["resume_events"] += 1
        save_state(state)

    if args.yes or not sys.stdin.isatty():
        print("Proceeding without prompt (--yes or non-interactive stdin).")
    else:
        confirm = input("Proceed? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    _migrate_legacy_pending(state)
    save_state(state)

    # ── Main loop — concurrent across (prompt, model) pairs ───────────────────
    # PROMPT_WORKERS threads pull from the queue; the global 20-RPM token bucket
    # in config/llm.py is the hard ceiling, and per-provider locks naturally
    # serialize calls to shared providers (e.g. all judge calls share nvidia/).
    try:
        with tqdm(total=len(todo_pairs), unit="pair", desc="Evaluating") as pbar, \
             ThreadPoolExecutor(max_workers=PROMPT_WORKERS) as pool:
            futures = {
                pool.submit(process_pair, p, m, state): (p["id"], m)
                for p, m in todo_pairs
            }
            try:
                for fut in as_completed(futures):
                    try:
                        fut.result()
                    except _QuotaSignal:
                        # Cancel everything still queued and schedule next run
                        for f in futures:
                            f.cancel()
                        log_exhaustion_and_schedule_next_run(state)
                        sys.exit(0)
                    pbar.update(1)
            except KeyboardInterrupt:
                for f in futures:
                    f.cancel()
                raise

        # ── Completion ────────────────────────────────────────────────────────
        final_set = load_completed_pairs()
        final_completed = len(completed_pairs) + sum(
            1 for p, m in todo_pairs
            if (p["id"], m) in final_set
        )
        consolidate_rows_to_parquet()
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
    print(f"  Resume events:  {state['resume_events']}")
    if os.path.exists(FINAL_CSV_PATH):
        print(f"  CSV output:     {FINAL_CSV_PATH}")
    if os.path.exists(METADATA_PATH):
        print(f"  Metadata:       {METADATA_PATH}")

    key_info_end = fetch_key_info()
    print()
    print_credit_status("Credits (post-run)", key_info_end)

    start = state.get("credits_at_start") or {}
    start_usage = start.get("usage")
    end_usage = (key_info_end or {}).get("usage")
    if start_usage is not None and end_usage is not None:
        spent = end_usage - start_usage
        marker = "  WARNING — non-zero credit spend detected!" if spent > 0.01 else ""
        print(f"    spent this run: ${spent:.4f}{marker}")


if __name__ == "__main__":
    main()
