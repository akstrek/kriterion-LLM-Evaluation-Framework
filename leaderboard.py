"""
leaderboard.py
Aggregates data/eval_results.csv → data/leaderboard.csv.

Two overall scores per model:
  overall_applicable  — mean of present (non-NaN) per-row dim scores
  overall_strict      — per-row NaN dims imputed with the model's own dim mean,
                        then averaged. Penalises models the judge couldn't
                        score on a dim (no free pass for skipping).

Plus bootstrap 95% CI on overall_applicable (1000× resample, pure numpy).
"""
import json
import os
import sys

import numpy as np
import pandas as pd

EVAL_RESULTS_PATH = os.path.join("data", "eval_results.csv")
LEADERBOARD_PATH  = os.path.join("data", "leaderboard.csv")

DIMENSIONS = ["factuality", "reasoning", "instruction_following", "format_compliance"]
CATEGORIES = [
    "factual_recall",
    "multi_step_reasoning",
    "instruction_following",
    "code_generation",
    "adversarial_edge_cases",
]

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
    return df


def load_prompts_category_map() -> dict[str, str]:
    path = os.path.join("prompts", "prompt_suite.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        prompts = json.load(f)
    return {p["id"]: p["category"] for p in prompts}


def compute_overall_strict_row(row: pd.Series, model_dim_means: dict[str, float]) -> float:
    """Per-row strict overall: NaN dims imputed with the model's own dim mean."""
    vals = []
    for dim in DIMENSIONS:
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
    category_map = load_prompts_category_map()
    if category_map:
        df = df.copy()
        df["category"] = df["prompt_id"].map(category_map)

    rows = []
    for model, group in df.groupby("model"):
        row: dict = {"model": model}
        # Per-dimension averages (NaN-aware).
        model_dim_means: dict[str, float] = {}
        for dim in DIMENSIONS:
            mean = group[dim].mean(skipna=True)
            model_dim_means[dim] = mean
            row[f"avg_{dim}"] = round(mean, 4) if not pd.isna(mean) else None

        # overall_applicable: row-wise nanmean of present dims, then column mean.
        if "overall_applicable" in group.columns:
            applicable_per_row = group["overall_applicable"].to_numpy(dtype=float)
        else:
            applicable_per_row = group[DIMENSIONS].apply(
                lambda r: np.nanmean(r.values), axis=1
            ).to_numpy(dtype=float)
        row["overall_applicable"] = round(float(np.nanmean(applicable_per_row)), 4)

        # overall_strict: impute NaN dims with model's own mean per row.
        strict_per_row = group.apply(
            lambda r: compute_overall_strict_row(r, model_dim_means), axis=1
        ).to_numpy(dtype=float)
        row["overall_strict"] = round(float(np.nanmean(strict_per_row)), 4)

        # Bootstrap CI on overall_applicable (pure numpy).
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

        # Per-category breakdown — uses the new overall_applicable column.
        if "category" in df.columns and "overall_applicable" in group.columns:
            for cat in CATEGORIES:
                cat_group = group[group["category"] == cat]
                row[f"cat_{cat}"] = (
                    round(cat_group["overall_applicable"].mean(), 4)
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


def print_leaderboard(lb: pd.DataFrame) -> None:
    print("\n" + "=" * 100)
    print("KRITERION LEADERBOARD")
    print("=" * 100)
    col_order = [
        "rank", "model", "overall_applicable", "overall_strict", "ci_low", "ci_high",
        "avg_factuality", "avg_reasoning",
        "avg_instruction_following", "avg_format_compliance",
        "latency_p50_ms", "latency_p95_ms",
        "avg_tokens_used", "n_judge_empty", "n_fallback",
    ]
    col_order = [c for c in col_order if c in lb.columns]
    with pd.option_context("display.max_columns", None, "display.width", 220,
                           "display.float_format", "{:.4f}".format):
        print(lb[col_order].to_string(index=False))
    print("=" * 100)


def main() -> None:
    df = load_results()
    print(f"Loaded {len(df)} rows from {EVAL_RESULTS_PATH}")
    lb = compute_leaderboard(df)
    os.makedirs("data", exist_ok=True)
    lb.to_csv(LEADERBOARD_PATH, index=False)
    print(f"\nLeaderboard saved: {LEADERBOARD_PATH}")
    print_leaderboard(lb)


if __name__ == "__main__":
    main()
