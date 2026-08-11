"""
retune_weights.py
Advisory HTB provider-weight recompute (closes the architecture.md §7 gap:
"HTB provider weights are still hand-set, not learned").

Reads data/eval_results.parquet (observed fallback rates -> demand
redirected onto the fallback's provider) and data/failed_calls.json (429
pressure, eval-stage only), and prints a proposed _PROVIDER_RATES dict next
to the current one, plus the resulting _split_eval_budget() RPD split.

ADVISORY ONLY. This script never writes to config/llm.py or anywhere else —
a human reads the proposal and applies the diff by hand. Auto-editing live
quota config from historical logs is how you get a self-inflicted outage.

Run: python retune_weights.py [--since YYYY-MM-DD] [--include-archives] [--json]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict

import pandas as pd

# Windows: default cp1252 stdout can't encode the em-dash used in the report
# banner below. PowerShell renders UTF-8 fine; this just tells Python's
# stdout wrapper to use it (same fix as batch_eval.py).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

from config.llm import (
    EVALUATOR_MODELS,
    FALLBACK_MAP,
    JUDGE_MODEL,
    _EVAL_PROVIDERS,
    _EVAL_RPD,
    _PROVIDER_RATES,
)

DATA_DIR     = "data"
PARQUET_PATH = os.path.join(DATA_DIR, "eval_results.parquet")
FAILED_PATH  = os.path.join(DATA_DIR, "failed_calls.json")
STATE_PATH   = os.path.join(DATA_DIR, "eval_state.json")

MIN_WEIGHT_FLOOR = 0.02
_ERROR_CODE_RE = re.compile(r"Error code:\s*(\d+)")


def _provider_of_model(model_id: str) -> str:
    return model_id.split("/")[0]


# ── Loading ──────────────────────────────────────────────────────────────────

def load_eval_results(path: str = PARQUET_PATH) -> "pd.DataFrame | None":
    if not os.path.exists(path):
        return None
    return pd.read_parquet(path)


def _default_since() -> "str | None":
    """Approximate the current run's start date from eval_state.json's
    started_at, so multi-run failed_calls.json history (never trimmed,
    duplicates across resumes) doesn't dilute the signal for the run that
    actually produced the current parquet."""
    if not os.path.exists(STATE_PATH):
        return None
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            state = json.load(f)
        started_at = state.get("started_at")
        return started_at[:10] if started_at else None
    except Exception:
        return None


def load_failed_calls(since: "str | None", include_archives: bool) -> list[dict]:
    """Union of the live failed_calls.json and, if requested, rotated
    failed_calls_<date>.json archives (see batch_eval.rotate_failed_calls_if_fresh).
    Filters to timestamp[:10] >= since when since is given."""
    paths = {FAILED_PATH}
    if include_archives:
        paths |= set(glob.glob(os.path.join(DATA_DIR, "failed_calls_*.json")))
    entries: list[dict] = []
    for path in sorted(paths):
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                entries.extend(loaded)
        except Exception:
            continue
    if since:
        entries = [e for e in entries if str(e.get("timestamp", ""))[:10] >= since]
    return entries


# ── Demand model ───────────────────────────────────────────────────────────────

def compute_demand(df: "pd.DataFrame | None") -> dict[str, float]:
    """Per-provider call demand: primary (1 per pair, attributed to the
    requested model's own provider) + fallback-redirected (observed
    fallback rate x pair count, routed through the live FALLBACK_MAP).

    The parquet's `model` column is always the *requested* id, even when
    fallback_triggered=True means the call actually landed on
    FALLBACK_MAP[model]'s provider (this asymmetry caused the historical
    deepseek ghost-lane bug — see architecture.md "Stale-row leak fixed").
    Fallback demand must be routed through FALLBACK_MAP, never inferred
    from the parquet."""
    demand: dict[str, float] = {p: 0.0 for p in _EVAL_PROVIDERS}
    if df is None or df.empty or "model" not in df.columns:
        return demand

    for model in EVALUATOR_MODELS:
        rows = df[df["model"] == model]
        n = len(rows)
        if n == 0:
            continue

        provider = _provider_of_model(model)
        if provider in demand:
            demand[provider] += n  # primary demand: 1 call per pair

        fb_id = FALLBACK_MAP.get(model)
        if fb_id is None or "fallback_triggered" not in rows.columns:
            continue
        fallback_rate = float(rows["fallback_triggered"].mean())
        fb_provider = _provider_of_model(fb_id)
        if fb_provider in demand:
            demand[fb_provider] += fallback_rate * n

    return demand


# ── Pressure model ─────────────────────────────────────────────────────────────

def compute_pressure(entries: list[dict]) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """Per-provider daily-peak 429 count, eval-stage entries only — both
    judge stages ("judge") also append to failed_calls.json, but a
    judge-lane 429 (nvidia/poolside) must not shift eval weights.

    Malformed `error` strings (no 'Error code: N' substring) bucket as
    "other" and are excluded from the 429 count rather than crashing.
    Returns (daily_peak_by_provider, raw_daily_counts_by_provider)."""
    daily_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for entry in entries:
        if entry.get("stage") != "eval":
            continue
        model = entry.get("model") or ""
        provider = _provider_of_model(model) if model else "unknown"
        match = _ERROR_CODE_RE.search(str(entry.get("error") or ""))
        code = match.group(1) if match else "other"
        if code != "429":
            continue
        day = str(entry.get("timestamp") or "")[:10] or "unknown"
        daily_counts[provider][day] += 1

    daily_peak = {p: max(days.values()) for p, days in daily_counts.items() if days}
    raw = {p: dict(days) for p, days in daily_counts.items()}
    return daily_peak, raw


# ── Proposal rule ──────────────────────────────────────────────────────────────

def propose_rates(demand: dict[str, float]) -> dict[str, float]:
    """Proposed weight is proportional to demand share, renormalized to the
    same total weight mass currently assigned across the eval lanes (the
    judge lane is untouched — it isn't in _EVAL_PROVIDERS). A provider with
    zero observed demand (fresh model swap) is floored, not NaN'd."""
    current_mass = sum(_PROVIDER_RATES[p] for p in _EVAL_PROVIDERS)
    total_demand = sum(demand.values())
    if total_demand <= 0:
        return {p: MIN_WEIGHT_FLOOR for p in _EVAL_PROVIDERS}
    proposed = {}
    for p in _EVAL_PROVIDERS:
        share = demand.get(p, 0.0) / total_demand
        proposed[p] = max(MIN_WEIGHT_FLOOR, round(share * current_mass, 4))
    return proposed


def split_eval_budget_with_rates(rates: dict[str, float]) -> dict[str, int]:
    """Exact replica of config.llm._split_eval_budget()'s formula, including
    the fractional-remainder-to-highest-weight rule. That function reads the
    module-global _PROVIDER_RATES directly, so it can't be called with a
    proposed dict — this must be kept in sync with config/llm.py by hand if
    that formula ever changes."""
    weights = {p: rates[p] for p in _EVAL_PROVIDERS}
    total_w = sum(weights.values())
    if total_w <= 0:
        return {p: 0 for p in _EVAL_PROVIDERS}
    raw = {p: _EVAL_RPD * w / total_w for p, w in weights.items()}
    out = {p: int(raw[p]) for p in _EVAL_PROVIDERS}
    leftover = _EVAL_RPD - sum(out.values())
    if leftover > 0:
        top = max(_EVAL_PROVIDERS, key=lambda p: weights[p])
        out[top] += leftover
    return out


# ── Report ─────────────────────────────────────────────────────────────────────

def print_report(*, current_rates, proposed_rates, current_split, proposed_split,
                  demand, daily_peak, raw_daily, n_entries, since, has_parquet) -> None:
    bar = "=" * 78
    print(bar)
    print("KRITERION — retune_weights.py  (ADVISORY — config/llm.py is NOT modified)")
    print(bar)
    print(f"  Eval providers:  {list(_EVAL_PROVIDERS)}")
    print(f"  Judge model:     {JUDGE_MODEL}  (untouched — not an eval lane)")
    print(f"  Eval results:    {'data/eval_results.parquet found' if has_parquet else 'NOT FOUND — demand is 0 for every lane'}")
    print(f"  failed_calls.json entries analyzed: {n_entries}" +
          (f"  (since {since})" if since else "  (no --since filter)"))
    print()
    print("  Demand (primary + fallback-redirected calls observed):")
    for p in _EVAL_PROVIDERS:
        print(f"    {p:12s} {demand.get(p, 0.0):8.1f}")
    print()
    print("  429 pressure (daily-peak count, eval-stage only):")
    for p in _EVAL_PROVIDERS:
        peak = daily_peak.get(p, 0)
        by_day = raw_daily.get(p, {})
        print(f"    {p:12s} peak={peak:4d}  by-day={by_day}")
    print()
    print("  Provider weight — current -> proposed:")
    for p in _EVAL_PROVIDERS:
        print(f"    {p:12s} {current_rates[p]:.4f}  ->  {proposed_rates[p]:.4f}")
    print()
    print("  _split_eval_budget() RPD split — current -> proposed:")
    for p in _EVAL_PROVIDERS:
        print(f"    {p:12s} {current_split[p]:4d}  ->  {proposed_split[p]:4d}")
    print(bar)
    print("  Advisory only — this script never writes to config/llm.py.")
    print("  If this proposal looks right, apply the _PROVIDER_RATES diff by hand.")
    print(bar)


# ── Main ───────────────────────────────────────────────────────────────────────

def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                    help="Only count failed_calls.json entries on/after this date. "
                         "Default: the current run's started_at date from "
                         "data/eval_state.json, or unfiltered if unavailable.")
    p.add_argument("--include-archives", action="store_true",
                    help="Also include rotated data/failed_calls_<date>.json archives.")
    p.add_argument("--json", action="store_true",
                    help="Emit machine-readable JSON instead of the printed report.")
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = _parse_args(argv)

    df = load_eval_results()
    since = args.since or _default_since()
    entries = load_failed_calls(since, args.include_archives)

    demand = compute_demand(df)
    daily_peak, raw_daily = compute_pressure(entries)
    proposed_rates = propose_rates(demand)
    current_rates = {p: _PROVIDER_RATES[p] for p in _EVAL_PROVIDERS}
    current_split = split_eval_budget_with_rates(_PROVIDER_RATES)
    proposed_split = split_eval_budget_with_rates(proposed_rates)

    if args.json:
        print(json.dumps({
            "eval_providers": list(_EVAL_PROVIDERS),
            "since": since,
            "n_failed_entries_analyzed": len(entries),
            "has_parquet": df is not None,
            "demand": demand,
            "pressure_daily_peak_429": daily_peak,
            "pressure_daily_raw_429": raw_daily,
            "current_rates": current_rates,
            "proposed_rates": proposed_rates,
            "current_rpd_split": current_split,
            "proposed_rpd_split": proposed_split,
        }, indent=2))
    else:
        print_report(
            current_rates=current_rates, proposed_rates=proposed_rates,
            current_split=current_split, proposed_split=proposed_split,
            demand=demand, daily_peak=daily_peak, raw_daily=raw_daily,
            n_entries=len(entries), since=since, has_parquet=df is not None,
        )

    if df is None:
        print(
            "\n  NOTE: data/eval_results.parquet not found — every lane's demand is 0. "
            "Run batch_eval.py first for a meaningful proposal.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
