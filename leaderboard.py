"""
leaderboard.py
Loads data/eval_results.csv and computes the leaderboard.

Outputs:
  data/leaderboard.csv
  Console table

Run: python leaderboard.py
"""
import os
import sys

import numpy as np
import pandas as pd

EVAL_RESULTS_PATH  = os.path.join("data", "eval_results.csv")
LEADERBOARD_PATH   = os.path.join("data", "leaderboard.csv")

DIMENSIONS = ["factuality", "reasoning", "instruction_following", "format_compliance"]
CATEGORIES = [
    "factual_recall",
    "multi_step_reasoning",
    "instruction_following",
    "code_generation",
    "adversarial_edge_cases",
]


def load_results() -> pd.DataFrame:
    if not os.path.exists(EVAL_RESULTS_PATH):
        sys.exit(
            f"ERROR: {EVAL_RESULTS_PATH} not found. "
            "Run batch_eval.py first."
        )
    df = pd.read_csv(EVAL_RESULTS_PATH)
    required = set(DIMENSIONS + ["model", "prompt_id", "overall_score", "latency_ms", "cost_usd"])
    missing = required - set(df.columns)
    if missing:
        sys.exit(f"ERROR: eval_results.csv is missing columns: {missing}")
    return df


def load_prompts_category_map() -> dict[str, str]:
    """Map prompt_id → category using prompt_suite.json if available."""
    import json
    path = os.path.join("prompts", "prompt_suite.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        prompts = json.load(f)
    return {p["id"]: p["category"] for p in prompts}


def compute_leaderboard(df: pd.DataFrame) -> pd.DataFrame:
    category_map = load_prompts_category_map()
    if category_map:
        df = df.copy()
        df["category"] = df["prompt_id"].map(category_map)

    rows = []

    for model, group in df.groupby("model"):
        row: dict = {"model": model}

        # Per-dimension averages
        for dim in DIMENSIONS:
            row[f"avg_{dim}"] = round(group[dim].mean(), 4)

        # Overall average (mean of 4 dimension averages, not mean of overall_score column)
        row["overall_avg"] = round(
            sum(row[f"avg_{dim}"] for dim in DIMENSIONS) / len(DIMENSIONS), 4
        )

        # Latency p50 / p95
        row["latency_p50_ms"] = int(np.percentile(group["latency_ms"].dropna(), 50))
        row["latency_p95_ms"] = int(np.percentile(group["latency_ms"].dropna(), 95))

        # Tokens and cost
        row["avg_tokens_used"]  = round(group["tokens_used"].mean(), 1) if "tokens_used" in group.columns else "N/A"
        total_cost              = group["cost_usd"].sum() if "cost_usd" in group.columns else 0.0
        row["total_cost_usd"]   = round(total_cost, 6)
        row["avg_cost_per_prompt_usd"] = round(total_cost / max(len(group), 1), 6)

        # Score per dollar (meaningful only when cost > 0)
        if total_cost > 0:
            row["score_per_dollar"] = round(row["overall_avg"] / total_cost, 4)
        else:
            row["score_per_dollar"] = "N/A (free tier)"

        # Per-category breakdown
        if "category" in df.columns:
            for cat in CATEGORIES:
                cat_group = group[group["category"] == cat]
                if len(cat_group) > 0:
                    row[f"cat_{cat}"] = round(cat_group["overall_score"].mean(), 4)
                else:
                    row[f"cat_{cat}"] = None
        else:
            for cat in CATEGORIES:
                row[f"cat_{cat}"] = None

        row["n_prompts"] = len(group)
        rows.append(row)

    leaderboard = pd.DataFrame(rows)
    leaderboard = leaderboard.sort_values("overall_avg", ascending=False).reset_index(drop=True)
    leaderboard.insert(0, "rank", leaderboard.index + 1)
    return leaderboard


def print_leaderboard(lb: pd.DataFrame) -> None:
    print("\n" + "=" * 90)
    print("KRITERION LEADERBOARD")
    print("=" * 90)

    col_order = [
        "rank", "model", "overall_avg",
        "avg_factuality", "avg_reasoning",
        "avg_instruction_following", "avg_format_compliance",
        "latency_p50_ms", "latency_p95_ms",
        "avg_tokens_used", "avg_cost_per_prompt_usd", "score_per_dollar",
    ]
    col_order = [c for c in col_order if c in lb.columns]

    with pd.option_context(
        "display.max_columns", None,
        "display.width", 200,
        "display.float_format", "{:.4f}".format,
    ):
        print(lb[col_order].to_string(index=False))

    print("\n── Category breakdown ──")
    cat_cols = ["model"] + [f"cat_{c}" for c in CATEGORIES if f"cat_{c}" in lb.columns]
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(lb[cat_cols].to_string(index=False))

    print("=" * 90)


def main() -> None:
    df = load_results()
    print(f"Loaded {len(df)} rows from {EVAL_RESULTS_PATH}")
    print(f"Models found: {sorted(df['model'].unique())}")

    lb = compute_leaderboard(df)

    os.makedirs("data", exist_ok=True)
    lb.to_csv(LEADERBOARD_PATH, index=False)
    print(f"\nLeaderboard saved to: {LEADERBOARD_PATH}")

    print_leaderboard(lb)


if __name__ == "__main__":
    main()
