"""
batch_eval.py
Daily eval runner built on the HTB + DRR architecture.

Architecture:
  - config.scheduler.EvalOrchestrator owns the worker pool and DRR fairness.
  - config.llm.call_model enforces rate limits, retries, and one fallback hop.
  - Quota exhaustion → orchestrator sleeps until 00:01 UTC and resumes
    (no schtasks .bat, no separate process).
  - Per-row parquet files for atomic O(1) checkpointing; consolidated to
    eval_results.parquet + eval_results.csv on completion.

Run: python batch_eval.py [-y]
"""
import argparse
import datetime
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from datetime import timezone

import math

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from tqdm import tqdm

from config.llm import (
    EVALUATOR_MODELS,
    JUDGE_MODEL,
    OPENROUTER_API_KEY,
    htb_status,
)
from config.scheduler import EvalOrchestrator
from evaluator import run_model, score_response


def _short_model(model_id: str) -> str:
    """Trim 'provider/foo-bar:free' → 'provider/foo-bar' for compact display."""
    return model_id.replace(":free", "")


def _one_line(text: str, max_chars: int = 90) -> str:
    out = (text or "").strip().replace("\n", " ").replace("\r", " ")
    if len(out) > max_chars:
        out = out[: max_chars - 1] + "…"
    return out


def _fmt_score(v) -> str:
    try:
        if v is None or math.isnan(float(v)):
            return " nan"
    except (TypeError, ValueError):
        return " nan"
    return f"{float(v):.2f}"

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR          = "data"
ROWS_DIR          = os.path.join(DATA_DIR, "rows")
PROMPT_SUITE_PATH = os.path.join("prompts", "prompt_suite.json")
PARQUET_PATH      = os.path.join(DATA_DIR, "eval_results.parquet")
STATE_PATH        = os.path.join(DATA_DIR, "eval_state.json")
FAILED_PATH       = os.path.join(DATA_DIR, "failed_calls.json")
METADATA_PATH     = os.path.join(DATA_DIR, "eval_metadata.json")
FINAL_CSV_PATH    = os.path.join(DATA_DIR, "eval_results.csv")


# ── New parquet schema (existing rows are NOT migrated) ──────────────────────
_SCHEMA = pa.schema([
    pa.field("prompt_id",              pa.string()),
    pa.field("model",                  pa.string()),
    pa.field("factuality",             pa.float64()),
    pa.field("reasoning",              pa.float64()),
    pa.field("instruction_following",  pa.float64()),
    pa.field("format_compliance",      pa.float64()),
    pa.field("overall_applicable",     pa.float64()),
    pa.field("judge_empty",            pa.bool_()),
    pa.field("fallback_triggered",     pa.bool_()),
    pa.field("retry_count",            pa.int32()),
    pa.field("latency_ms",             pa.int64()),
    pa.field("tokens_used",            pa.int64()),
    pa.field("cost_usd",               pa.float64()),
    pa.field("provider",               pa.string()),
    pa.field("day_of_run",             pa.int32()),
    pa.field("judge_model",            pa.string()),
    pa.field("parse_error",            pa.string()),
    pa.field("judge_latency_ms",       pa.int64()),
    pa.field("judge_tokens_used",      pa.int64()),
])


# ── State I/O ─────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {
            "total_calls":     0,
            "total_failures":  0,
            "resume_events":   0,
            "day_of_run":      1,
            "started_at":      datetime.datetime.now(timezone.utc).isoformat(),
            "htb_snapshot":    htb_status(),
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


def load_completed_pairs() -> set[tuple[str, str]]:
    """Union of legacy single-file parquet and the per-row directory.
    Stale rows whose model is no longer in EVALUATOR_MODELS (e.g. a model
    that was removed from the roster between runs) are ignored — otherwise
    they would silently mark (prompt_id, stale_model) as 'done' on resume
    and leak into the consolidated leaderboard."""
    active = set(EVALUATOR_MODELS)
    pairs: set[tuple[str, str]] = set()
    if os.path.exists(PARQUET_PATH):
        try:
            t = pq.read_table(PARQUET_PATH, columns=["prompt_id", "model"]).to_pandas()
            for pid, m in zip(t["prompt_id"], t["model"]):
                if m in active:
                    pairs.add((pid, m))
        except Exception:
            pass
    if os.path.isdir(ROWS_DIR):
        for fname in os.listdir(ROWS_DIR):
            if not fname.endswith(".parquet"):
                continue
            try:
                t = pq.read_table(os.path.join(ROWS_DIR, fname),
                                  columns=["prompt_id", "model"])
                if t.num_rows:
                    m = str(t["model"][0].as_py())
                    if m in active:
                        pairs.add((str(t["prompt_id"][0].as_py()), m))
            except Exception:
                continue
    return pairs


def append_row_to_parquet(row: dict) -> None:
    """Atomic per-row write: tmp → fsync → os.replace."""
    os.makedirs(ROWS_DIR, exist_ok=True)
    record = {
        "prompt_id":             str(row["prompt_id"]),
        "model":                 str(row["model"]),
        "factuality":            float(row["factuality"]),
        "reasoning":             float(row["reasoning"]),
        "instruction_following": float(row["instruction_following"]),
        "format_compliance":     float(row["format_compliance"]),
        "overall_applicable":    float(row["overall_applicable"]),
        "judge_empty":           bool(row["judge_empty"]),
        "fallback_triggered":    bool(row["fallback_triggered"]),
        "retry_count":           int(row["retry_count"]),
        "latency_ms":            int(row["latency_ms"]),
        "tokens_used":           int(row["tokens_used"]),
        "cost_usd":              0.0,
        "provider":              "openrouter",
        "day_of_run":            int(row["day_of_run"]),
        "judge_model":           str(row["judge_model"]),
        "parse_error":           str(row.get("parse_error") or ""),
        "judge_latency_ms":      int(row["judge_latency_ms"]),
        "judge_tokens_used":     int(row["judge_tokens_used"]),
    }
    table = pa.Table.from_pydict({k: [v] for k, v in record.items()}, schema=_SCHEMA)
    final = _row_path(record["prompt_id"], record["model"])
    tmp = final + ".tmp"
    pq.write_table(table, tmp)
    with open(tmp, "r+b") as f:
        os.fsync(f.fileno())
    os.replace(tmp, final)


def consolidate_rows_to_parquet() -> int:
    """Concat all per-row parquet files into eval_results.parquet, filtering
    out any rows whose model is no longer in EVALUATOR_MODELS so a roster
    change between runs doesn't leak stale lanes into the leaderboard."""
    active = pa.array(list(EVALUATOR_MODELS), type=pa.string())
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
    mask = pc.is_in(combined["model"], value_set=active)
    combined = combined.filter(mask)
    tmp = PARQUET_PATH + ".tmp"
    pq.write_table(combined, tmp)
    with open(tmp, "r+b") as f:
        os.fsync(f.fileno())
    os.replace(tmp, PARQUET_PATH)
    return combined.num_rows


# ── Failed calls log ──────────────────────────────────────────────────────────

def append_failed_call(entry: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    existing: list[dict] = []
    if os.path.exists(FAILED_PATH):
        try:
            with open(FAILED_PATH, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []
    existing.append(entry)
    tmp = FAILED_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, FAILED_PATH)


# ── Metadata ──────────────────────────────────────────────────────────────────

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
        "htb_snapshot":    htb_status(),
    }
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


# ── Credit telemetry ──────────────────────────────────────────────────────────

def fetch_key_info() -> dict | None:
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
    print(f"  {label}:")
    print(f"    usage:     ${usage:.4f}" if usage is not None else "    usage:     <n/a>")
    print(f"    limit:     ${limit:.4f}" if limit is not None else "    limit:     <unlimited>")
    if remaining is not None:
        print(f"    remaining: ${remaining:.4f}")


# ── Row builder ───────────────────────────────────────────────────────────────

def build_result_row(
    prompt_obj: dict,
    model: str,
    eval_result,
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
        "overall_applicable":    scores["overall_applicable"],
        "judge_empty":           scores["judge_empty"],
        "fallback_triggered":    eval_result.fallback_triggered or scores["fallback_triggered"],
        "retry_count":           int(eval_result.retry_count) + int(scores["retry_count"]),
        "latency_ms":            eval_result.latency_ms,
        "tokens_used":           eval_result.tokens_used,
        "judge_model":           scores["judge_model"],
        "parse_error":           scores.get("parse_error") or "",
        "judge_latency_ms":      scores["judge_latency_ms"],
        "judge_tokens_used":     scores["judge_tokens_used"],
        "day_of_run":            day_of_run,
    }


# ── Per-pair processor ────────────────────────────────────────────────────────

_STATE_LOCK = threading.Lock()


def make_process_pair(state: dict, pbar: "tqdm | None" = None):
    def _set_postfix(stage: str, model: str) -> None:
        if pbar is None:
            return
        try:
            pbar.set_postfix_str(f"{stage}={_short_model(model)}", refresh=False)
        except Exception:
            pass

    def _write(msg: str) -> None:
        if pbar is not None:
            tqdm.write(msg)
        else:
            print(msg, flush=True)

    def process_pair(prompt_obj: dict, model: str) -> None:
        pid = prompt_obj["id"]

        # Eval
        _set_postfix("eval", model)
        try:
            eval_result = run_model(prompt_obj["prompt_text"], model)
        except Exception as exc:
            from config.llm import DailyQuotaExhausted
            if isinstance(exc, DailyQuotaExhausted):
                raise
            append_failed_call({
                "prompt_id": pid, "model": model, "stage": "eval",
                "error": str(exc),
                "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
            })
            with _STATE_LOCK:
                state["total_failures"] += 1
                save_state(state)
            _write(f"[{pid}] EVAL FAIL  model={_short_model(model)}  err={exc}")
            if pbar is not None:
                pbar.update(1)
            return
        with _STATE_LOCK:
            state["total_calls"] += 1 + int(eval_result.retry_count)

        # Judge / score
        _set_postfix("judge", JUDGE_MODEL)
        try:
            scores = score_response(prompt_obj, eval_result.text)
        except Exception as exc:
            from config.llm import DailyQuotaExhausted
            if isinstance(exc, DailyQuotaExhausted):
                raise
            append_failed_call({
                "prompt_id": pid, "model": model, "stage": "judge",
                "error": str(exc),
                "eval_latency_ms": eval_result.latency_ms,
                "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
            })
            with _STATE_LOCK:
                state["total_failures"] += 1
                save_state(state)
            _write(f"[{pid}] JUDGE FAIL model={_short_model(model)}  err={exc}")
            if pbar is not None:
                pbar.update(1)
            return
        with _STATE_LOCK:
            state["total_calls"] += 1 + int(scores["retry_count"])
            day_of_run = state["day_of_run"]
            state["htb_snapshot"] = htb_status()
            save_state(state)

        row = build_result_row(prompt_obj, model, eval_result, scores, day_of_run)
        append_row_to_parquet(row)

        # ── Per-pair display ────────────────────────────────────────────────
        eval_snip = _one_line(eval_result.text)
        fb_tag = " [FALLBACK]" if eval_result.fallback_triggered else ""
        retry_tag = f" retry={eval_result.retry_count}" if eval_result.retry_count else ""
        if scores.get("judge_empty"):
            judge_line = (
                f"judge={_short_model(scores['judge_model'])} → <EMPTY/UNPARSEABLE> "
                f"err={scores.get('parse_error') or '?'}"
            )
        else:
            judge_line = (
                f"judge={_short_model(scores['judge_model'])} → "
                f"f={_fmt_score(scores['factuality'])} "
                f"r={_fmt_score(scores['reasoning'])} "
                f"i={_fmt_score(scores['instruction_following'])} "
                f"fc={_fmt_score(scores['format_compliance'])} "
                f"| overall={_fmt_score(scores['overall_applicable'])}"
            )
        _write(
            f"[{pid}] eval={_short_model(model)}{fb_tag}{retry_tag} "
            f"({eval_result.latency_ms}ms, {eval_result.tokens_used}t) → {eval_snip!r}\n"
            f"       {judge_line} ({scores['judge_latency_ms']}ms)"
        )
        if pbar is not None:
            pbar.update(1)

    return process_pair


# ── Main ──────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kriterion eval runner (HTB + DRR)")
    p.add_argument("-y", "--yes", action="store_true",
                   help="Skip interactive confirmation (required for non-interactive runs).")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    os.makedirs(DATA_DIR, exist_ok=True)

    prompts         = load_prompts()
    state           = load_state()
    completed_pairs = load_completed_pairs()

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

    print("\n" + "=" * 70)
    print("Kriterion Batch Evaluation  —  HTB + DRR runner")
    print("=" * 70)
    print(f"  Prompts:            {len(prompts)}")
    print(f"  Models:             {n_models}  ({n_models} worker threads)")
    print(f"  Total pairs:        {total_pairs}")
    print(f"  Completed:          {len(completed_pairs)}")
    print(f"  Remaining pairs:    {len(todo_pairs)}")
    print(f"  Day of run:         {state['day_of_run']}")
    print(f"  Total calls so far: {state['total_calls']}")
    print(f"  Failures logged:    {state['total_failures']}")
    print(f"  Resume events:      {state['resume_events']}")
    print(f"  Judge model:        {JUDGE_MODEL}")
    print()
    print_credit_status("Credits (pre-flight)", key_info_start)
    print()

    if not todo_pairs:
        print("Nothing to run — all pairs completed.")
        consolidate_rows_to_parquet()
        if os.path.exists(PARQUET_PATH):
            pq.read_table(PARQUET_PATH).to_pandas().to_csv(FINAL_CSV_PATH, index=False)
        save_metadata(state, len(completed_pairs), total_pairs)
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

    bar_fmt = (
        "{l_bar}{bar}| {n_fmt}/{total_fmt} pairs "
        "[{elapsed}<{remaining}, {rate_fmt}]{postfix}"
    )
    try:
        with tqdm(total=len(todo_pairs), desc="Evaluating", unit="pair",
                  bar_format=bar_fmt, dynamic_ncols=True) as pbar:
            orch = EvalOrchestrator(EVALUATOR_MODELS, make_process_pair(state, pbar))
            orch.enqueue_all(todo_pairs)
            stats = orch.run()
    except KeyboardInterrupt:
        print("\nInterrupted — state saved.", flush=True)
        sys.exit(0)

    final_set = load_completed_pairs()
    final_completed = len(completed_pairs) + sum(
        1 for p, m in todo_pairs if (p["id"], m) in final_set
    )
    consolidate_rows_to_parquet()
    if os.path.exists(PARQUET_PATH):
        pq.read_table(PARQUET_PATH).to_pandas().to_csv(FINAL_CSV_PATH, index=False)

    save_metadata(state, final_completed, total_pairs)

    print("\n── Run summary ──────────────────────────────────────────────────────")
    print(f"  Completed:      {stats.completed}")
    print(f"  Failed:         {stats.failed}")
    print(f"  Quota sleeps:   {stats.quota_sleeps}")
    print(f"  Total calls:    {state['total_calls']}")
    print(f"  Total failures: {state['total_failures']}")
    if os.path.exists(FINAL_CSV_PATH):
        print(f"  CSV output:     {FINAL_CSV_PATH}")

    key_info_end = fetch_key_info()
    print()
    print_credit_status("Credits (post-run)", key_info_end)
    start = state.get("credits_at_start") or {}
    s, e = start.get("usage"), (key_info_end or {}).get("usage")
    if s is not None and e is not None:
        spent = e - s
        marker = "  WARNING — non-zero credit spend!" if spent > 0.01 else ""
        print(f"    spent this run: ${spent:.4f}{marker}")


if __name__ == "__main__":
    main()
