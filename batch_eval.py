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
    RUBRIC_VERSION,
    _interruptible_sleep,
    htb_status,
)
from config.scheduler import EvalOrchestrator
from evaluator import run_model, score_response

# Windows: default cp1252 stdout can't encode the box-drawing chars used in the
# quota-exhaustion display blocks. PowerShell renders UTF-8 fine; this just
# tells Python's stdout wrapper to use it.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass


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

# ── Patient multi-pass sweep ────────────────────────────────────────────────
# Transient upstream 429s ("…temporarily rate-limited upstream. Please retry
# shortly") survive the in-call retry budget and are dropped to failed_calls.json
# without being requeued (only DailyQuotaExhausted gets the sleep-and-retry
# path). A single immediate re-run hits the same instantaneous throttle. So
# after a pass, if pairs are still un-evaluated, wait an increasing interval to
# let the upstream throttle clear, then re-run the orchestrator over only the
# remainder. Nothing inside the pass changes — this just adds spacing between
# passes, which is the one thing a manual re-run lacks.
SWEEP_MAX_PASSES  = 4                    # 1 initial pass + up to 3 retry sweeps
SWEEP_SLEEPS_SECS = [300, 900, 1800]     # gaps before sweeps 2, 3, 4 (5m/15m/30m)


# Response-text storage cap. Separate decision from evaluator.JUDGE_RESPONSE_MAX_CHARS
# (judge-input truncation) — this one bounds what's persisted per row so one
# adversarially-long completion can't balloon a row file. 20k chars covers every
# real response seen so far.
STORE_RESPONSE_MAX_CHARS = 20_000

# ── Parquet schema v2 (existing v1 rows are NOT migrated — see the startup
# guard in load_completed_pairs/consolidate_rows_to_parquet) ─────────────────
_SCHEMA = pa.schema([
    pa.field("prompt_id",              pa.string()),
    pa.field("model",                  pa.string()),
    pa.field("factuality",             pa.float64()),
    pa.field("reasoning",              pa.float64()),
    pa.field("instruction_following",  pa.float64()),
    pa.field("format_compliance",      pa.float64()),
    pa.field("verbosity",              pa.float64()),
    pa.field("judge_empty",            pa.bool_()),
    pa.field("fallback_triggered",     pa.bool_()),
    pa.field("retry_count",            pa.int32()),
    pa.field("latency_ms",             pa.int64()),
    pa.field("tokens_used",            pa.int64()),
    pa.field("cost_usd",               pa.float64()),
    pa.field("provider",               pa.string()),
    pa.field("day_of_run",             pa.int32()),
    pa.field("difficulty",             pa.string()),
    pa.field("judge_model",            pa.string()),
    pa.field("parse_error",            pa.string()),
    pa.field("judge_latency_ms",       pa.int64()),
    pa.field("judge_tokens_used",      pa.int64()),
    pa.field("response_text",          pa.string()),
    pa.field("response_truncated",     pa.bool_()),
    pa.field("gt_provided",            pa.bool_()),
    pa.field("rubric_version",         pa.int32()),
])


# ── State I/O ─────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {
            "total_calls":     0,
            "total_failures":  0,
            "resume_events":   0,
            "day_of_run":      1,
            "n_fallback":      0,
            "n_judge_empty":   0,
            "started_at":      datetime.datetime.now(timezone.utc).isoformat(),
            "htb_snapshot":    htb_status(),
        }
    with open(STATE_PATH, encoding="utf-8") as f:
        s = json.load(f)
    s.setdefault("n_fallback", 0)
    s.setdefault("n_judge_empty", 0)
    return s


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
        "verbosity":             float(row["verbosity"]),
        "judge_empty":           bool(row["judge_empty"]),
        "fallback_triggered":    bool(row["fallback_triggered"]),
        "retry_count":           int(row["retry_count"]),
        "latency_ms":            int(row["latency_ms"]),
        "tokens_used":           int(row["tokens_used"]),
        "cost_usd":              0.0,
        "provider":              "openrouter",
        "day_of_run":            int(row["day_of_run"]),
        "difficulty":            str(row.get("difficulty") or ""),
        "judge_model":           str(row["judge_model"]),
        "parse_error":           str(row.get("parse_error") or ""),
        "judge_latency_ms":      int(row["judge_latency_ms"]),
        "judge_tokens_used":     int(row["judge_tokens_used"]),
        "response_text":         str(row.get("response_text") or ""),
        "response_truncated":    bool(row.get("response_truncated", False)),
        "gt_provided":           bool(row.get("gt_provided", False)),
        "rubric_version":        int(row.get("rubric_version", RUBRIC_VERSION)),
    }
    table = pa.Table.from_pydict({k: [v] for k, v in record.items()}, schema=_SCHEMA)
    final = _row_path(record["prompt_id"], record["model"])
    tmp = final + ".tmp"
    pq.write_table(table, tmp)
    with open(tmp, "r+b") as f:
        os.fsync(f.fileno())
    os.replace(tmp, final)


_ARCHIVE_CMD = (
    r"mkdir data\_archive_v1_rows && move data\rows\*.parquet data\_archive_v1_rows\ "
).strip()


def _print_schema_guard_banner(fname: str, reason: str) -> None:
    lines = [
        "",
        _QUOTA_BOX_BAR,
        "  KRITERION — STALE ROW SCHEMA DETECTED, REFUSING TO START",
        _QUOTA_BOX_BAR,
        f"  File:     {fname}",
        f"  Reason:   {reason}",
        f"  Current rubric_version: {RUBRIC_VERSION}",
        _QUOTA_BOX_DIV,
        "  data/rows/ holds rows from an older schema. Mixing them with a new",
        "  run corrupts consolidation and silently drops the old run's data.",
        "  Move the old rows aside first, then re-run:",
        "",
        f"    {_ARCHIVE_CMD}",
        _QUOTA_BOX_BAR,
        "",
    ]
    print("\n".join(lines), flush=True)


def check_row_schema_guard() -> None:
    """Refuse to start if any row file predates the current RUBRIC_VERSION.

    Old rows are the only record of the published run — never auto-migrated
    or auto-deleted. Exits nonzero before any writes happen this run."""
    if not os.path.isdir(ROWS_DIR):
        return
    for fname in sorted(os.listdir(ROWS_DIR)):
        if not fname.endswith(".parquet"):
            continue
        path = os.path.join(ROWS_DIR, fname)
        try:
            schema = pq.read_schema(path)
        except Exception:
            continue  # unreadable file — consolidation will surface it later
        if "rubric_version" not in schema.names:
            _print_schema_guard_banner(fname, "rubric_version column missing (pre-schema-v2 row)")
            sys.exit(1)
        table = pq.read_table(path, columns=["rubric_version"])
        if table.num_rows and table["rubric_version"][0].as_py() < RUBRIC_VERSION:
            found = table["rubric_version"][0].as_py()
            _print_schema_guard_banner(fname, f"rubric_version={found} < current {RUBRIC_VERSION}")
            sys.exit(1)


def consolidate_rows_to_parquet() -> int:
    """Rebuild eval_results.parquet from the per-row checkpoints in ROWS_DIR.

    Each row file is the *latest* evaluation for its (prompt_id, model) pair
    (`append_row_to_parquet` writes via `os.replace`, overwriting in place), so
    the row directory is the single source of truth and naturally holds exactly
    one row per pair. We therefore rebuild from ROWS_DIR alone and deliberately
    do NOT re-read the existing eval_results.parquet — doing so re-appended every
    prior pass/run's rows on each consolidation, growing the file without bound
    (e.g. a 1,800-pair run ballooned to ~10,624 rows across four days, inflating
    n_prompts and artificially tightening the bootstrap CIs). Rows whose model is
    no longer in EVALUATOR_MODELS are filtered so a roster change between runs
    doesn't leak stale lanes into the leaderboard. A defensive de-dup on
    (prompt_id, model) keeps the last occurrence in case more than one row file
    ever maps to the same pair."""
    active = pa.array(list(EVALUATOR_MODELS), type=pa.string())
    tables = []
    fnames = []
    if os.path.isdir(ROWS_DIR):
        for fname in sorted(os.listdir(ROWS_DIR)):
            if fname.endswith(".parquet"):
                tables.append(pq.read_table(os.path.join(ROWS_DIR, fname)))
                fnames.append(fname)
    if not tables:
        return 0
    # Defensive: pyarrow's promote_options="default" would silently unify
    # mismatched schemas (e.g. a stray v1 row file) rather than erroring, which
    # would corrupt the consolidated output. The startup guard should catch
    # this first, but fail loudly here too rather than concat silently.
    base_schema = tables[0].schema
    for t, fname in zip(tables, fnames):
        if not t.schema.equals(base_schema):
            raise ValueError(
                f"Row schema mismatch in '{fname}': expected {base_schema.names}, "
                f"got {t.schema.names}. Mixed-version rows in {ROWS_DIR} — "
                f"move old rows aside: {_ARCHIVE_CMD}"
            )
    combined = pa.concat_tables(tables, promote_options="default")
    mask = pc.is_in(combined["model"], value_set=active)
    combined = combined.filter(mask)
    combined = _dedup_latest_pair(combined)
    tmp = PARQUET_PATH + ".tmp"
    pq.write_table(combined, tmp)
    with open(tmp, "r+b") as f:
        os.fsync(f.fileno())
    os.replace(tmp, PARQUET_PATH)
    return combined.num_rows


def _dedup_latest_pair(table: "pa.Table") -> "pa.Table":
    """Keep the last row per (prompt_id, model), preserving input order.

    Row files are unique per pair by construction, so this is a belt-and-braces
    guard; it makes consolidation idempotent even if a stray duplicate row ever
    reaches the table. Pure pyarrow — no pandas round-trip."""
    n = table.num_rows
    if n == 0:
        return table
    prompt_ids = table.column("prompt_id").to_pylist()
    models = table.column("model").to_pylist()
    # Walk forward recording the last index seen for each key, then take rows in
    # ascending index order so the output keeps the table's original ordering.
    last_index: dict[tuple[str, str], int] = {}
    for i in range(n):
        last_index[(prompt_ids[i], models[i])] = i
    keep = sorted(last_index.values())
    if len(keep) == n:
        return table
    return table.take(pa.array(keep, type=pa.int64()))


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
    response_text = eval_result.text or ""
    return {
        "prompt_id":             prompt_obj["id"],
        "model":                 model,
        "factuality":            scores["factuality"],
        "reasoning":             scores["reasoning"],
        "instruction_following": scores["instruction_following"],
        "format_compliance":     scores["format_compliance"],
        "verbosity":             scores["verbosity"],
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
        "difficulty":            prompt_obj.get("difficulty") or "",
        "response_text":         response_text[:STORE_RESPONSE_MAX_CHARS],
        "response_truncated":    bool(scores.get("response_truncated", False)),
        "gt_provided":           bool(scores.get("gt_provided", False)),
        "rubric_version":        RUBRIC_VERSION,
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
            if eval_result.fallback_triggered or scores.get("fallback_triggered"):
                state["n_fallback"] = state.get("n_fallback", 0) + 1
            if scores.get("judge_empty"):
                state["n_judge_empty"] = state.get("n_judge_empty", 0) + 1
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
                f"v={_fmt_score(scores['verbosity'])}"
            )
        _write(
            f"[{pid}] eval={_short_model(model)}{fb_tag}{retry_tag} "
            f"({eval_result.latency_ms}ms, {eval_result.tokens_used}t) → {eval_snip!r}\n"
            f"       {judge_line} ({scores['judge_latency_ms']}ms)"
        )
        if pbar is not None:
            pbar.update(1)

    return process_pair


# ── Quota-exhaustion display blocks ──────────────────────────────────────────
# Pure stdout. Reuses existing state values and htb_status() — no new source
# of truth for reset time, call counts, or fallback counts.

_QUOTA_BOX_BAR = "═" * 47
_QUOTA_BOX_DIV = "  " + "─" * 45


def _fmt_hh_mm(total_secs: float) -> tuple[int, int]:
    secs = max(0.0, total_secs)
    return int(secs // 3600), int((secs % 3600) // 60)


def _print_quota_exhausted_box(state: dict, completed: int, total: int,
                               reset_at: datetime.datetime) -> None:
    """Print the ONCE-per-sleep status block. Called by the on_quota_enter hook."""
    snap = htb_status()
    root = snap.get("root", {})
    daily_budget = int(root.get("daily_budget", 0))
    daily_remaining = int(root.get("daily_remaining", 0))
    calls_today = max(0, daily_budget - daily_remaining)

    utc_now = datetime.datetime.now(timezone.utc)
    remaining_pairs = max(0, total - completed)
    pct = round(completed / total * 100, 1) if total else 0.0
    hh, mm = _fmt_hh_mm((reset_at - utc_now).total_seconds())

    lines = [
        "",
        _QUOTA_BOX_BAR,
        "  KRITERION — DAILY QUOTA EXHAUSTED",
        _QUOTA_BOX_BAR,
        f"  Completed pairs:   {completed} / {total}   ({pct}%)",
        f"  Remaining pairs:   {remaining_pairs}",
        f"  Day of run:        {state.get('day_of_run', '?')}",
        f"  Calls used today:  {calls_today} / {daily_budget}",
        f"  Fallbacks used:    {state.get('n_fallback', 0)}",
        _QUOTA_BOX_DIV,
        f"  UTC now:           {utc_now:%Y-%m-%d %H:%M:%S} UTC",
        f"  Quota resets:      {reset_at:%Y-%m-%d %H:%M:%S} UTC",
        f"  Time until reset:  {hh}h {mm}m",
        _QUOTA_BOX_DIV,
        "  Sleeping in-process. Resumes automatically at reset.",
        "  Safe to leave running. Checkpoints are on disk —",
        "  Ctrl+C and re-run resumes from the same point.",
        _QUOTA_BOX_BAR,
        "",
    ]
    print("\n".join(lines), flush=True)


def _print_wake_tick(reset_at: datetime.datetime, remaining_secs: float) -> None:
    """Compact heartbeat line, fires once per ~5-min poll iteration."""
    utc_now = datetime.datetime.now(timezone.utc)
    hh, mm = _fmt_hh_mm(remaining_secs)
    print(f"  [wake-check] {utc_now:%H:%M:%S} UTC — {hh}h {mm}m until reset",
          flush=True)


def _print_resume_banner(state: dict) -> None:
    utc_now = datetime.datetime.now(timezone.utc)
    print(f"  RESUMING — quota reset detected at "
          f"{utc_now:%Y-%m-%d %H:%M:%S} UTC. Day {state.get('day_of_run', '?')}.",
          flush=True)


def _print_completion_box(state: dict, completed: int, total: int) -> None:
    lines = [
        "",
        _QUOTA_BOX_BAR,
        "  KRITERION — RUN COMPLETE",
        _QUOTA_BOX_BAR,
        f"  Completed pairs:    {completed} / {total}",
        f"  Total days elapsed: {state.get('day_of_run', '?')}",
        f"  Total fallbacks:    {state.get('n_fallback', 0)}",
        f"  Judge-empty rows:   {state.get('n_judge_empty', 0)}",
        _QUOTA_BOX_DIV,
        "  Run complete. Run leaderboard.py next.",
        _QUOTA_BOX_BAR,
        "",
    ]
    print("\n".join(lines), flush=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kriterion eval runner (HTB + DRR)")
    p.add_argument("-y", "--yes", action="store_true",
                   help="Skip interactive confirmation (required for non-interactive runs).")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    os.makedirs(DATA_DIR, exist_ok=True)
    check_row_schema_guard()

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
        _print_completion_box(state, len(completed_pairs), total_pairs)
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

    # Hooks share live state via closure. orch_holder is a one-element list so
    # the closures can read orch.stats.completed after orch is constructed.
    orch_holder: list = []
    initial_completed = len(completed_pairs)

    def _live_completed() -> int:
        if not orch_holder:
            return initial_completed
        return initial_completed + int(orch_holder[0].stats.completed)

    def on_quota_enter(reset_at: datetime.datetime) -> None:
        _print_quota_exhausted_box(state, _live_completed(), total_pairs, reset_at)

    def on_quota_tick(reset_at: datetime.datetime, remaining_secs: float) -> None:
        _print_wake_tick(reset_at, remaining_secs)

    def on_quota_resume() -> None:
        # A natural wake means we slept through a UTC day boundary; bump
        # day_of_run so the next batch of rows is tagged with the new day.
        with _STATE_LOCK:
            state["day_of_run"] = int(state.get("day_of_run", 1)) + 1
            save_state(state)
        _print_resume_banner(state)

    def run_one_pass(pairs: list, pass_idx: int):
        """One full orchestrator pass over `pairs`. Reuses the existing
        EvalOrchestrator + quota callbacks verbatim — the sweep adds nothing
        inside a pass, only spacing between passes."""
        nonlocal initial_completed
        # Rebind the live-completed baseline + holder so the quota status box
        # reports correct totals on a later sweep (new orch → stats.completed
        # resets to 0 each pass).
        initial_completed = len(load_completed_pairs())
        with tqdm(total=len(pairs), desc=f"Evaluating (pass {pass_idx + 1})",
                  unit="pair", bar_format=bar_fmt, dynamic_ncols=True) as pbar:
            orch = EvalOrchestrator(
                EVALUATOR_MODELS,
                make_process_pair(state, pbar),
                on_quota_enter=on_quota_enter,
                on_quota_tick=on_quota_tick,
                on_quota_resume=on_quota_resume,
            )
            orch_holder[:] = [orch]
            orch.enqueue_all(pairs)
            return orch.run()

    remaining = todo_pairs
    sweep_completed = sweep_failed = sweep_quota_sleeps = 0
    try:
        for pass_idx in range(SWEEP_MAX_PASSES):
            stats = run_one_pass(remaining, pass_idx)
            sweep_completed += stats.completed
            sweep_failed += stats.failed
            sweep_quota_sleeps += stats.quota_sleeps

            # Only pairs that wrote a parquet row are truly done; transient-429
            # failures left no row and stay in `remaining`.
            done_now = load_completed_pairs()
            remaining = [
                (p, m) for (p, m) in remaining if (p["id"], m) not in done_now
            ]
            if not remaining or pass_idx == SWEEP_MAX_PASSES - 1:
                break

            delay = SWEEP_SLEEPS_SECS[min(pass_idx, len(SWEEP_SLEEPS_SECS) - 1)]
            print(
                f"\n  {len(remaining)} pair(s) still failing on transient 429 — "
                f"sweep {pass_idx + 2}/{SWEEP_MAX_PASSES} in {delay // 60} min "
                f"(letting upstream throttle clear)…",
                flush=True,
            )
            _interruptible_sleep(delay)
    except KeyboardInterrupt:
        print("\n  Interrupted — checkpoints saved, re-run to resume.", flush=True)
        sys.exit(0)

    if remaining:
        print(
            f"\n  {len(remaining)} pair(s) still un-evaluated after "
            f"{SWEEP_MAX_PASSES} passes (persistent upstream throttle) — "
            f"re-run later to retry.",
            flush=True,
        )

    final_set = load_completed_pairs()
    final_completed = len(completed_pairs) + sum(
        1 for p, m in todo_pairs if (p["id"], m) in final_set
    )
    consolidate_rows_to_parquet()
    if os.path.exists(PARQUET_PATH):
        pq.read_table(PARQUET_PATH).to_pandas().to_csv(FINAL_CSV_PATH, index=False)

    save_metadata(state, final_completed, total_pairs)

    if final_completed >= total_pairs:
        _print_completion_box(state, final_completed, total_pairs)

    print("\n── Run summary ──────────────────────────────────────────────────────")
    print(f"  Completed:      {sweep_completed}")
    print(f"  Failed:         {sweep_failed}")
    print(f"  Quota sleeps:   {sweep_quota_sleeps}")
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
