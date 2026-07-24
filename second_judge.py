"""
second_judge.py
Offline re-scoring of a deterministic ~17% stratified sample of stored
schema-v2 rows with a second, architecturally-independent judge model.

Produces data/judge_agreement.csv: inter-judge agreement (Pearson r, MAE,
% within one rubric-anchor step) per dimension + one 'overall' row (the
4-dim headline mean). This is the artifact that converts README's "single
judge — same-family bias is possible" into a measured number.

Judge 2's scores are NEVER blended into the leaderboard. See
PLAN-multi-judge-ensemble.md for full design rationale.

Requires: data/eval_results.parquet built under schema v2 (rubric_version,
response_text columns present) — i.e. a batch_eval.py run after
PLAN-grounded-judging-schema-v2.md landed. Running against the current v1
parquet exits nonzero with a clear message; this is testable today.

Run (real, burns poolside judge2 quota):  python second_judge.py --yes
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from batch_eval import _safe_model_filename
from config.llm import (
    EVALUATOR_MODELS,
    JUDGE2_MODEL,
    JUDGE_SYSTEM_PROMPT,
    call_model,
)
from evaluator import build_judge_user_message, parse_judge_json
from leaderboard import DIMENSIONS, HEADLINE_DIMS

DATA_DIR          = "data"
PARQUET_PATH      = os.path.join(DATA_DIR, "eval_results.parquet")
ROWS2_DIR         = os.path.join(DATA_DIR, "judge2_rows")
PROMPT_SUITE_PATH = os.path.join("prompts", "prompt_suite.json")
AGREEMENT_PATH    = os.path.join(DATA_DIR, "judge_agreement.csv")
LEADERBOARD_GUARD_PATHS = [
    os.path.join(DATA_DIR, "leaderboard.csv"),
    os.path.join(DATA_DIR, "leaderboard_by_difficulty.csv"),
    os.path.join("public", "data", "leaderboard.csv"),
    os.path.join("public", "data", "leaderboard_by_difficulty.csv"),
]

SAMPLE_MOD        = 6      # pair sampled iff hash % SAMPLE_MOD == 0 -> ~1/6 of pairs
PER_MODEL_TARGET  = 100    # exact count enforced per evaluator model after truncate/extend
ONE_STEP          = 0.25   # rubric anchors are spaced 0.15-0.30 apart; 0.25 splits that gap
JUDGE2_RPD        = 350    # config.llm._JUDGE2_RPD — poolside's daily budget

AGREEMENT_FIELDS = [
    "dim", "n", "pearson_r", "mae", "pct_within_one_step",
    "n_judge1_nan_judge2_val", "n_judge2_nan_judge1_val", "n_fallback_scored",
]

_ROWS2_SCHEMA = pa.schema([
    pa.field("prompt_id",              pa.string()),
    pa.field("model",                  pa.string()),
    pa.field("factuality2",            pa.float64()),
    pa.field("reasoning2",             pa.float64()),
    pa.field("instruction_following2", pa.float64()),
    pa.field("format_compliance2",     pa.float64()),
    pa.field("verbosity2",             pa.float64()),
    pa.field("judge2_model",           pa.string()),
    pa.field("judge2_empty",           pa.bool_()),
    pa.field("parse_error2",           pa.string()),
    pa.field("judge2_latency_ms",      pa.int64()),
])


# ── Schema-v2 guard ────────────────────────────────────────────────────────────

def load_v2_results(path: str = PARQUET_PATH) -> pd.DataFrame:
    """Load eval_results.parquet; exit with a clear message if it predates
    schema v2 (no response_text to re-score, no rubric_version to check)."""
    if not os.path.exists(path):
        sys.exit(f"ERROR: {path} not found. Run batch_eval.py requires schema-v2 results; "
                  "see PLAN-grounded-judging-schema-v2.md")
    df = pq.read_table(path).to_pandas()
    if "response_text" not in df.columns or "rubric_version" not in df.columns:
        sys.exit(
            "ERROR: eval_results.parquet lacks schema-v2 columns (response_text/rubric_version). "
            "second_judge.py requires schema-v2 results; see PLAN-grounded-judging-schema-v2.md"
        )
    versions = sorted({int(v) for v in df["rubric_version"].dropna().unique()})
    if not versions or versions[0] < 2:
        sys.exit(
            f"ERROR: rubric_version {versions or '<missing>'} predates v2. "
            "second_judge.py requires schema-v2 results; see PLAN-grounded-judging-schema-v2.md"
        )
    if len(versions) > 1:
        sys.exit(f"ERROR: eval_results.parquet mixes rubric_version {versions} — re-run against "
                  "a single-version dataset before sampling for judge agreement.")
    return df


# ── Deterministic stratified sampling ─────────────────────────────────────────

def _pair_hash(prompt_id: str, model: str) -> int:
    return int(hashlib.md5(f"{prompt_id}|{model}".encode("utf-8")).hexdigest(), 16)


def sample_pairs(pairs: list[tuple[str, str]], per_model: int = PER_MODEL_TARGET,
                  mod: int = SAMPLE_MOD) -> list[tuple[str, str]]:
    """Deterministic stratified sample: no RNG state, stable across re-runs/resumes.

    A pair is selected iff md5(f"{prompt_id}|{model}") mod `mod` == 0 (~1/mod of
    pairs). Then, per model, truncated/extended to exactly `per_model` pairs —
    both steps ordered by the same hash, so results are byte-identical across
    invocations and unaffected by any other model's pairs.
    """
    by_model: dict[str, list[tuple[str, str]]] = {}
    for pid, model in pairs:
        by_model.setdefault(model, []).append((pid, model))

    result: list[tuple[str, str]] = []
    for model, model_pairs in by_model.items():
        all_sorted = sorted(model_pairs, key=lambda pm: _pair_hash(pm[0], pm[1]))
        selected = [pm for pm in all_sorted if _pair_hash(pm[0], pm[1]) % mod == 0]

        if len(selected) > per_model:
            selected = selected[:per_model]
        elif len(selected) < per_model:
            selected_set = set(selected)
            for pm in all_sorted:
                if len(selected) >= per_model:
                    break
                if pm not in selected_set:
                    selected.append(pm)
                    selected_set.add(pm)
            selected = sorted(selected, key=lambda pm: _pair_hash(pm[0], pm[1]))

        result.extend(selected)
    return result


def print_stratification_table(sampled_pairs: list[tuple[str, str]],
                                difficulty_by_pid: dict[str, str]) -> None:
    counts = Counter((model, difficulty_by_pid.get(pid, "?")) for pid, model in sampled_pairs)
    print(f"\nStratification of {len(sampled_pairs)} sampled pairs (model x difficulty):")
    models = sorted({m for m, _ in counts})
    for model in models:
        per_diff = {d: n for (m, d), n in counts.items() if m == model}
        total = sum(per_diff.values())
        breakdown = ", ".join(f"{d}={n}" for d, n in sorted(per_diff.items()))
        print(f"  {model:<40} total={total:<4} ({breakdown})")


# ── Row I/O (per-pair checkpointing, mirrors batch_eval.append_row_to_parquet) ─

def _row2_path(prompt_id: str, model: str, rows_dir: str = ROWS2_DIR) -> str:
    return os.path.join(rows_dir, f"{prompt_id}__{_safe_model_filename(model)}.parquet")


def load_completed_judge2_pairs(rows_dir: str = ROWS2_DIR) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    if not os.path.isdir(rows_dir):
        return pairs
    for fname in os.listdir(rows_dir):
        if not fname.endswith(".parquet"):
            continue
        try:
            t = pq.read_table(os.path.join(rows_dir, fname), columns=["prompt_id", "model"])
            if t.num_rows:
                pairs.add((str(t["prompt_id"][0].as_py()), str(t["model"][0].as_py())))
        except Exception:
            continue
    return pairs


def append_judge2_row(row: dict, rows_dir: str = ROWS2_DIR) -> None:
    """Atomic per-row write: tmp -> fsync -> os.replace (same idiom as batch_eval)."""
    os.makedirs(rows_dir, exist_ok=True)
    record = {
        "prompt_id":              str(row["prompt_id"]),
        "model":                  str(row["model"]),
        "factuality2":            float(row["factuality"]),
        "reasoning2":             float(row["reasoning"]),
        "instruction_following2": float(row["instruction_following"]),
        "format_compliance2":     float(row["format_compliance"]),
        "verbosity2":             float(row["verbosity"]),
        "judge2_model":           str(row["judge2_model"]),
        "judge2_empty":           bool(row["judge2_empty"]),
        "parse_error2":           str(row.get("parse_error2") or ""),
        "judge2_latency_ms":      int(row["judge2_latency_ms"]),
    }
    table = pa.Table.from_pydict({k: [v] for k, v in record.items()}, schema=_ROWS2_SCHEMA)
    final = _row2_path(record["prompt_id"], record["model"], rows_dir)
    tmp = final + ".tmp"
    pq.write_table(table, tmp)
    with open(tmp, "r+b") as f:
        os.fsync(f.fileno())
    os.replace(tmp, final)


def load_judge2_rows(rows_dir: str = ROWS2_DIR) -> pd.DataFrame:
    if not os.path.isdir(rows_dir):
        return pd.DataFrame(columns=[f.name for f in _ROWS2_SCHEMA])
    tables = [
        pq.read_table(os.path.join(rows_dir, fname))
        for fname in sorted(os.listdir(rows_dir))
        if fname.endswith(".parquet")
    ]
    if not tables:
        return pd.DataFrame(columns=[f.name for f in _ROWS2_SCHEMA])
    return pa.concat_tables(tables).to_pandas()


# ── Scoring ────────────────────────────────────────────────────────────────────

_JUDGE2_EMPTY_PREFIXES = ("Empty judge response", "JSONDecodeError", "Judge returned non-object")


def score_pair_with_judge2(prompt_obj: dict, response_text: str, *,
                            client=None, tree=None, throttle=None) -> dict:
    """Re-score one (prompt, response) pair with judge 2. Rebuilds the judge
    user message via evaluator.build_judge_user_message — the same function
    judge 1 used — so disagreement measures judge bias, not prompt drift."""
    message, _ = build_judge_user_message(prompt_obj, response_text)
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user",   "content": message},
    ]
    call_kwargs = {}
    if client is not None:
        call_kwargs["client"] = client
    if tree is not None:
        call_kwargs["tree"] = tree
    if throttle is not None:
        call_kwargs["throttle"] = throttle

    result = call_model(model_id=JUDGE2_MODEL, messages=messages, role="judge2", **call_kwargs)
    scores, parse_error = parse_judge_json(result.text)
    judge2_empty = parse_error is not None and parse_error.startswith(_JUDGE2_EMPTY_PREFIXES)
    return {
        **scores,
        "judge2_model":      result.model_used,
        "judge2_empty":      judge2_empty,
        "parse_error2":      parse_error or "",
        "judge2_latency_ms": result.latency_ms,
    }


def run_second_judge(sampled_pairs: list[tuple[str, str]], prompts_by_id: dict[str, dict],
                      response_by_pair: dict[tuple[str, str], str], *,
                      client=None, tree=None, throttle=None, rows_dir: str = ROWS2_DIR) -> int:
    """Score every sampled pair not already checkpointed. Returns count scored."""
    completed = load_completed_judge2_pairs(rows_dir)
    todo = [p for p in sampled_pairs if p not in completed]
    for prompt_id, model in todo:
        prompt_obj = prompts_by_id[prompt_id]
        response_text = response_by_pair[(prompt_id, model)]
        scored = score_pair_with_judge2(prompt_obj, response_text, client=client, tree=tree, throttle=throttle)
        row = {"prompt_id": prompt_id, "model": model, **scored}
        append_judge2_row(row, rows_dir)
    return len(todo)


# ── Agreement aggregation ──────────────────────────────────────────────────────

def _agreement_stats(judge1: pd.Series, judge2: pd.Series, is_fallback: pd.Series) -> dict:
    """Agreement stats between two aligned score series (index-matched).

    NaN != disagreement about magnitude: rows where exactly one side is NaN
    are pulled into separate null-disagreement counters, never into MAE/r
    (which would either NaN-propagate or require corrupting imputation).
    Fallback-scored rows are excluded from the headline stats and counted
    separately — a fallback-scored pair measures the fallback model, not
    JUDGE2_MODEL, so pooling it would misattribute disagreement.
    """
    both_valid = judge1.notna() & judge2.notna()
    primary_valid = both_valid & ~is_fallback
    n_fallback = int((both_valid & is_fallback).sum())

    a = judge1[primary_valid].to_numpy(dtype=float)
    b = judge2[primary_valid].to_numpy(dtype=float)
    n = len(a)

    if n >= 2 and np.std(a) > 0 and np.std(b) > 0:
        pearson_r: float | str = float(np.corrcoef(a, b)[0, 1])
    else:
        pearson_r = ""  # undefined (zero variance) or too few points — rely on pct_within_one_step

    mae = float(np.mean(np.abs(a - b))) if n else float("nan")
    pct_within_one_step = float(np.mean(np.abs(a - b) <= ONE_STEP)) if n else float("nan")

    n_judge1_nan_judge2_val = int((judge1.isna() & judge2.notna()).sum())
    n_judge2_nan_judge1_val = int((judge1.notna() & judge2.isna()).sum())

    return {
        "n": n,
        "pearson_r": pearson_r,
        "mae": mae,
        "pct_within_one_step": pct_within_one_step,
        "n_judge1_nan_judge2_val": n_judge1_nan_judge2_val,
        "n_judge2_nan_judge1_val": n_judge2_nan_judge1_val,
        "n_fallback_scored": n_fallback,
    }


def aggregate_agreement(judge1_df: pd.DataFrame, judge2_df: pd.DataFrame) -> list[dict]:
    """One row per dimension + one 'overall' row (4-dim headline mean),
    joined on (prompt_id, model). Only pairs present in both frames count."""
    merged = judge2_df.merge(
        judge1_df[["prompt_id", "model"] + DIMENSIONS],
        on=["prompt_id", "model"], how="inner", suffixes=("", "_j1"),
    )
    is_fallback = merged["judge2_model"] != JUDGE2_MODEL

    rows = []
    for dim in DIMENSIONS:
        stats = _agreement_stats(merged[dim], merged[f"{dim}2"], is_fallback)
        rows.append({"dim": dim, **stats})

    # 'overall': row-wise nanmean over HEADLINE_DIMS per judge (mirrors
    # leaderboard.py's overall_applicable), then agreement between the two means.
    j1_overall = merged[HEADLINE_DIMS].mean(axis=1, skipna=True)
    j2_overall = merged[[f"{d}2" for d in HEADLINE_DIMS]].mean(axis=1, skipna=True)
    # mean(skipna=True) over an all-NaN row yields NaN already — no special-casing needed.
    stats = _agreement_stats(j1_overall, j2_overall, is_fallback)
    rows.append({"dim": "overall", **stats})
    return rows


def write_agreement_csv(rows: list[dict], path: str = AGREEMENT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df = pd.DataFrame(rows, columns=AGREEMENT_FIELDS)
    df.to_csv(path, index=False)


# ── Leaderboard-untouched guard ───────────────────────────────────────────────

def _hash_if_exists(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Second-judge inter-judge agreement sampler")
    parser.add_argument("--yes", action="store_true",
                         help="Confirm burning real poolside judge2-model quota (required for a real run).")
    args = parser.parse_args()

    before_hashes = {p: _hash_if_exists(p) for p in LEADERBOARD_GUARD_PATHS}

    df1 = load_v2_results()

    with open(PROMPT_SUITE_PATH, encoding="utf-8") as f:
        prompts = json.load(f)
    prompts_by_id = {p["id"]: p for p in prompts}
    difficulty_by_pid = {p["id"]: p.get("difficulty", "?") for p in prompts}

    active = set(EVALUATOR_MODELS)
    universe = [(pid, m) for pid, m in zip(df1["prompt_id"], df1["model"]) if m in active]
    sampled = sample_pairs(universe)
    print_stratification_table(sampled, difficulty_by_pid)

    completed = load_completed_judge2_pairs()
    todo_count = len([p for p in sampled if p not in completed])
    print(f"\n{len(sampled)} sampled pairs, {len(completed)} already scored, "
          f"{todo_count} calls needed — uses ~{todo_count} of poolside's {JUDGE2_RPD} RPD "
          f"judge2 budget. Do not run alongside a main eval pass.")
    if len(sampled) > JUDGE2_RPD:
        sys.exit(f"ERROR: {len(sampled)} sampled pairs exceeds the {JUDGE2_RPD} RPD judge2 budget. Refusing to run.")
    if not args.yes:
        sys.exit("Refusing to run without --yes (this burns real poolside judge2-model quota). "
                  "Re-run with --yes to proceed.")

    response_by_pair = {
        (pid, m): (rt or "")
        for pid, m, rt in zip(df1["prompt_id"], df1["model"], df1["response_text"])
    }

    n_scored = run_second_judge(sampled, prompts_by_id, response_by_pair)
    print(f"Scored {n_scored} new pairs with judge 2 ({JUDGE2_MODEL}).")

    df2 = load_judge2_rows()
    rows = aggregate_agreement(df1, df2)
    write_agreement_csv(rows)
    print(f"\nWrote {AGREEMENT_PATH} ({len(rows)} rows)")
    for r in rows:
        pr = r["pearson_r"] if r["pearson_r"] != "" else "n/a"
        print(f"  {r['dim']:<22} n={r['n']:<4} r={pr}  mae={r['mae']:.3f}  "
              f"within_1_step={r['pct_within_one_step']:.2f}  fallback={r['n_fallback_scored']}")

    after_hashes = {p: _hash_if_exists(p) for p in LEADERBOARD_GUARD_PATHS}
    if before_hashes != after_hashes:
        sys.exit("ERROR: leaderboard CSV(s) changed during second_judge.py — this must never happen "
                  "(judge 2 scores are never blended into the headline). Aborting.")


if __name__ == "__main__":
    main()
