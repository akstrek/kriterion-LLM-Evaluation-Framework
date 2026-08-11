"""
leaderboard.py
Aggregates data/eval_results.csv → data/leaderboard.csv
                                  + data/leaderboard_by_difficulty.csv

Single source of truth for the headline policy:
  HEADLINE_DIMS = factuality + reasoning + instruction_following + verbosity
  format_compliance is still scored on every prompt and aggregated as
  avg_format_compliance, but it is NOT part of overall_applicable —
  format pickiness is a separate axis, reported but not averaged in.

  overall_applicable  — row-wise nanmean over HEADLINE_DIMS, then column mean
  overall_strict      — per-row NaN headline dims imputed with the model's
                        own dim mean, then averaged. No free pass for dims
                        the judge couldn't score.

Plus bootstrap 95% CI on overall_applicable (1000× resample, pure numpy).

Stratified output:
  data/leaderboard_by_difficulty.csv  — per (model × difficulty) row with
  overall_applicable + per-dim means + n_prompts. This is the view that
  separates models at the expert tier; the headline mixes all tiers.
"""
import json
import os
import shutil
import sys

import numpy as np
import pandas as pd

EVAL_RESULTS_PATH       = os.path.join("data", "eval_results.csv")
LEADERBOARD_PATH        = os.path.join("data", "leaderboard.csv")
LEADERBOARD_BY_DIFF_PATH = os.path.join("data", "leaderboard_by_difficulty.csv")
JUDGE_CALIBRATION_PATH  = os.path.join("data", "judge_calibration.csv")
JUDGE_AGREEMENT_PATH    = os.path.join("data", "judge_agreement.csv")
RESULTS_BY_PROMPT_PATH  = os.path.join("data", "results_by_prompt.csv")
PROMPTS_PATH            = os.path.join("prompts", "prompt_suite.json")
PUBLIC_DATA_DIR         = os.path.join("public", "data")

# Single source of truth pair: this list mirrors evaluator.EXPECTED_SCORE_KEYS.
# Keep in sync.
DIMENSIONS = [
    "factuality",
    "reasoning",
    "instruction_following",
    "format_compliance",
    "verbosity",
]

# Headline policy: format_compliance is reported but NOT in the headline mean.
HEADLINE_DIMS = [
    "factuality",
    "reasoning",
    "instruction_following",
    "verbosity",
]

CATEGORIES = [
    "factual_recall",
    "multi_step_reasoning",
    "instruction_following",
    "code_generation",
    "safety_calibration",
    "hallucination_under_uncertainty",
]

DIFFICULTY_TIERS = ["easy", "medium", "hard", "expert"]

BOOTSTRAP_ITERS = 1000
BOOTSTRAP_SEED  = 42


def load_results() -> pd.DataFrame:
    if not os.path.exists(EVAL_RESULTS_PATH):
        sys.exit(f"ERROR: {EVAL_RESULTS_PATH} not found. Run batch_eval.py first.")
    df = pd.read_csv(EVAL_RESULTS_PATH)
    required = set(DIMENSIONS + ["model", "prompt_id", "latency_ms"])
    missing = required - set(df.columns)
    if missing:
        sys.exit(f"ERROR: eval_results.csv missing columns: {missing}")
    if "rubric_version" in df.columns:
        versions = df["rubric_version"].dropna().unique()
        if len(versions) > 1:
            sys.exit(
                f"ERROR: eval_results.csv mixes rubric_version values {sorted(versions)} — "
                "grounded (v2) and ungrounded (v1) factuality scores are not comparable. "
                "Re-run against a single-version dataset."
            )
    return df


def load_prompts_metadata() -> tuple[dict[str, str], dict[str, str]]:
    """Returns (category_map, difficulty_map) keyed by prompt id.

    Falls back to empty dicts if prompt_suite.json is missing; downstream
    aggregations skip stratified outputs when difficulty is unknown.
    """
    if not os.path.exists(PROMPTS_PATH):
        return {}, {}
    with open(PROMPTS_PATH, encoding="utf-8") as f:
        prompts = json.load(f)
    cat_map = {p["id"]: p["category"] for p in prompts}
    diff_map = {p["id"]: p.get("difficulty", "") for p in prompts}
    return cat_map, diff_map


def _row_headline_mean(row: pd.Series) -> float:
    """Row-wise nanmean over the 4 headline dims."""
    return float(np.nanmean([row[d] for d in HEADLINE_DIMS]))


def compute_overall_strict_row(row: pd.Series, model_dim_means: dict[str, float]) -> float:
    """Per-row strict overall: NaN headline dims imputed with the model's own dim mean."""
    vals = []
    for dim in HEADLINE_DIMS:
        v = row[dim]
        if pd.isna(v):
            v = model_dim_means.get(dim, np.nan)
        vals.append(v)
    return float(np.nanmean(vals))


def bootstrap_ci(values: np.ndarray, iters: int = BOOTSTRAP_ITERS,
                 seed: int = BOOTSTRAP_SEED) -> tuple[float, float]:
    values = values[~np.isnan(values)]
    if len(values) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    n = len(values)
    means = np.empty(iters, dtype=float)
    for i in range(iters):
        sample = values[rng.integers(0, n, size=n)]
        means[i] = np.nanmean(sample)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def compute_leaderboard(df: pd.DataFrame) -> pd.DataFrame:
    cat_map, diff_map = load_prompts_metadata()
    if cat_map:
        df = df.copy()
        df["category"] = df["prompt_id"].map(cat_map)
    if diff_map and "difficulty" not in df.columns:
        df["difficulty"] = df["prompt_id"].map(diff_map)

    # Compute per-row headline mean once; reused for cat_* breakdown.
    applicable_all = df[HEADLINE_DIMS].apply(_row_headline_mean, axis=1)
    df = df.assign(_applicable=applicable_all)

    rows = []
    for model, group in df.groupby("model"):
        row: dict = {"model": model}

        # Per-dimension averages — all 5 dims reported (incl. format_compliance).
        model_dim_means: dict[str, float] = {}
        for dim in DIMENSIONS:
            mean = group[dim].mean(skipna=True)
            model_dim_means[dim] = mean
            row[f"avg_{dim}"] = round(mean, 4) if not pd.isna(mean) else None

        # overall_applicable: nanmean of the row-wise headline means.
        applicable_per_row = group["_applicable"].to_numpy(dtype=float)
        row["overall_applicable"] = round(float(np.nanmean(applicable_per_row)), 4)

        # overall_strict: impute NaN headline dims with model's own mean per row.
        strict_per_row = group.apply(
            lambda r: compute_overall_strict_row(r, model_dim_means), axis=1
        ).to_numpy(dtype=float)
        row["overall_strict"] = round(float(np.nanmean(strict_per_row)), 4)

        # Bootstrap CI on overall_applicable.
        lo, hi = bootstrap_ci(applicable_per_row)
        row["ci_low"]  = round(lo, 4) if not np.isnan(lo) else None
        row["ci_high"] = round(hi, 4) if not np.isnan(hi) else None

        # Latency and tokens.
        lat = group["latency_ms"].dropna()
        row["latency_p50_ms"] = int(np.percentile(lat, 50)) if len(lat) else None
        row["latency_p95_ms"] = int(np.percentile(lat, 95)) if len(lat) else None
        row["avg_tokens_used"] = (
            round(group["tokens_used"].mean(), 1) if "tokens_used" in group.columns else None
        )
        total_cost = group["cost_usd"].sum() if "cost_usd" in group.columns else 0.0
        row["total_cost_usd"] = round(total_cost, 6)
        row["avg_cost_per_prompt_usd"] = round(total_cost / max(len(group), 1), 6)
        row["score_per_dollar"] = (
            round(row["overall_applicable"] / total_cost, 4)
            if total_cost > 0 else "N/A (free tier)"
        )

        # Per-category breakdown — row-wise headline mean averaged per category.
        if "category" in df.columns:
            for cat in CATEGORIES:
                cat_group = group[group["category"] == cat]
                row[f"cat_{cat}"] = (
                    round(float(np.nanmean(cat_group["_applicable"])), 4)
                    if len(cat_group) > 0 else None
                )
        else:
            for cat in CATEGORIES:
                row[f"cat_{cat}"] = None

        # Diagnostic counts.
        row["n_prompts"] = len(group)
        if "judge_empty" in group.columns:
            row["n_judge_empty"] = int(group["judge_empty"].sum())
        if "fallback_triggered" in group.columns:
            row["n_fallback"] = int(group["fallback_triggered"].sum())

        rows.append(row)

    lb = pd.DataFrame(rows)
    lb = lb.sort_values("overall_applicable", ascending=False).reset_index(drop=True)
    lb.insert(0, "rank", lb.index + 1)
    return lb


def compute_leaderboard_by_difficulty(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (model × difficulty). Same headline policy as compute_leaderboard,
    but stratified. Empty when no `difficulty` column is present."""
    if "difficulty" not in df.columns:
        return pd.DataFrame()
    if "_applicable" not in df.columns:
        df = df.assign(_applicable=df[HEADLINE_DIMS].apply(_row_headline_mean, axis=1))

    rows = []
    for (model, difficulty), group in df.groupby(["model", "difficulty"], dropna=False):
        if not difficulty or (isinstance(difficulty, float) and np.isnan(difficulty)):
            continue  # rows without a difficulty tag (legacy data) are skipped
        applicable_per_row = group["_applicable"].to_numpy(dtype=float)
        row: dict = {
            "model": model,
            "difficulty": difficulty,
            "overall_applicable": round(float(np.nanmean(applicable_per_row)), 4),
            "n_prompts": len(group),
        }
        for dim in DIMENSIONS:
            mean = group[dim].mean(skipna=True)
            row[f"avg_{dim}"] = round(mean, 4) if not pd.isna(mean) else None
        rows.append(row)

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Order by model name then by difficulty tier (canonical easy → expert).
    tier_order = {t: i for i, t in enumerate(DIFFICULTY_TIERS)}
    out["_tier_ord"] = out["difficulty"].map(lambda t: tier_order.get(t, 99))
    out = out.sort_values(["model", "_tier_ord"]).drop(columns=["_tier_ord"]).reset_index(drop=True)
    return out


def export_by_prompt(df: pd.DataFrame, prompts_path: str = PROMPTS_PATH) -> pd.DataFrame:
    """One row per (prompt_id, model): category (joined from the prompt suite — never
    in the parquet/CSV), difficulty, per-dim scores, and overall_applicable_row.

    category is looked up per row rather than assumed symmetric with the results
    frame: a result whose prompt_id no longer exists in the suite gets category
    "unknown" (warned, not dropped or crashed) — see architecture.md ghost-lane note.
    """
    meta: dict = {}
    if os.path.exists(prompts_path):
        with open(prompts_path, encoding="utf-8") as f:
            meta = {p["id"]: p for p in json.load(f)}

    categories = df["prompt_id"].map(lambda pid: meta.get(pid, {}).get("category"))
    missing_mask = categories.isna()
    if missing_mask.any():
        missing_ids = sorted(df.loc[missing_mask, "prompt_id"].unique())
        print(
            f"WARNING: {len(missing_ids)} prompt_id(s) in {EVAL_RESULTS_PATH} not found "
            f"in {prompts_path}; category set to 'unknown': {missing_ids}"
        )
    categories = categories.fillna("unknown")

    applicable = df[HEADLINE_DIMS].apply(_row_headline_mean, axis=1)

    out = pd.DataFrame({
        "prompt_id": df["prompt_id"],
        "category": categories,
        "difficulty": df["difficulty"] if "difficulty" in df.columns else "",
        "model": df["model"],
    })
    for dim in DIMENSIONS:
        out[dim] = df[dim]
    out["overall_applicable_row"] = applicable
    out["judge_empty"] = df["judge_empty"] if "judge_empty" in df.columns else False
    out["fallback_triggered"] = df["fallback_triggered"] if "fallback_triggered" in df.columns else False
    out["latency_ms"] = df["latency_ms"]
    return out


def _publish_to_public(paths: list[str]) -> None:
    """Copy CSVs into public/data/ so the static frontend can fetch them.
    No-op if the destination directory doesn't exist (e.g. backend-only checkout)."""
    if not os.path.isdir(PUBLIC_DATA_DIR):
        return
    for src in paths:
        if os.path.exists(src):
            dst = os.path.join(PUBLIC_DATA_DIR, os.path.basename(src))
            shutil.copyfile(src, dst)


def print_leaderboard(lb: pd.DataFrame) -> None:
    print("\n" + "=" * 110)
    print("KRITERION LEADERBOARD")
    print("=" * 110)
    col_order = [
        "rank", "model", "overall_applicable", "overall_strict", "ci_low", "ci_high",
        "avg_factuality", "avg_reasoning",
        "avg_instruction_following", "avg_format_compliance", "avg_verbosity",
        "latency_p50_ms", "latency_p95_ms",
        "avg_tokens_used", "n_judge_empty", "n_fallback",
    ]
    col_order = [c for c in col_order if c in lb.columns]
    with pd.option_context("display.max_columns", None, "display.width", 240,
                           "display.float_format", "{:.4f}".format):
        print(lb[col_order].to_string(index=False))
    print("=" * 110)


def main() -> None:
    df = load_results()
    print(f"Loaded {len(df)} rows from {EVAL_RESULTS_PATH}")

    lb = compute_leaderboard(df)
    os.makedirs("data", exist_ok=True)
    lb.to_csv(LEADERBOARD_PATH, index=False)
    print(f"\nLeaderboard saved: {LEADERBOARD_PATH}")

    lb_diff = compute_leaderboard_by_difficulty(df)
    if not lb_diff.empty:
        lb_diff.to_csv(LEADERBOARD_BY_DIFF_PATH, index=False)
        print(f"By-difficulty saved: {LEADERBOARD_BY_DIFF_PATH}  ({len(lb_diff)} rows)")
    else:
        print("By-difficulty: skipped (no difficulty tags in input).")

    by_prompt = export_by_prompt(df)
    by_prompt.to_csv(RESULTS_BY_PROMPT_PATH, index=False)
    print(f"By-prompt saved: {RESULTS_BY_PROMPT_PATH}  ({len(by_prompt)} rows)")

    _publish_to_public([LEADERBOARD_PATH, LEADERBOARD_BY_DIFF_PATH, JUDGE_CALIBRATION_PATH,
                         JUDGE_AGREEMENT_PATH, RESULTS_BY_PROMPT_PATH])
    print_leaderboard(lb)


if __name__ == "__main__":
    main()
