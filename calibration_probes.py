"""
calibration_probes.py
Runner for judge calibration probes — measures the judge's reliability against
known-quality anchor (prompt, response) pairs with pre-agreed expected score bands.

Outputs:
  data/calibration_runs.csv    — one row per (probe, run): the raw evidence.
  data/judge_calibration.csv   — one row per dimension: the published artifact,
                                  copied to public/data/ by leaderboard.py.

Run (real, burns nvidia judge quota):  python calibration_probes.py --yes
Dry run (offline, mocked, no network): python calibration_probes.py --dry-run

Uses 32 probes x REPEATS=3 = 96 judge calls against nvidia's 300 RPD budget —
do not run alongside a main eval pass (see JUDGE_RPD check in main()).
"""
import argparse
import csv
import json
import math
import os
import statistics
import sys
import tempfile
from unittest.mock import MagicMock

from config.llm import JUDGE_MODEL, JUDGE_SYSTEM_PROMPT, HTBTree, AdaptiveThrottle, call_model
from evaluator import parse_judge_json

PROBES_PATH = os.path.join("prompts", "calibration_probes.json")
DATA_DIR    = "data"

DIMENSIONS = ["factuality", "reasoning", "instruction_following", "format_compliance", "verbosity"]
REPEATS    = 3
JUDGE_RPD  = 300  # config.llm._JUDGE_RPD — the nvidia judge leaf's daily budget.

REQUIRED_PROBE_KEYS = {
    "probe_id", "target_dim", "prompt_text", "response_text",
    "expected", "applicable_dims", "rationale",
}

RUN_FIELDS = [
    "probe_id", "target_dim", "run_idx", "score",
    "expected_low", "expected_high", "within_band",
    "judge_model", "parse_error",
]
SUMMARY_FIELDS = [
    "dim", "n_probes", "n_runs", "band_hit_rate",
    "mae_vs_band_midpoint", "test_retest_std",
    "n_parse_failures", "n_fallback_scored",
]


def load_probes(path: str = PROBES_PATH) -> list[dict]:
    """Load + validate the probe suite. Fails fast with a clear message."""
    with open(path, encoding="utf-8") as f:
        probes = json.load(f)

    seen_ids: set[str] = set()
    for p in probes:
        missing = REQUIRED_PROBE_KEYS - set(p)
        if missing:
            sys.exit(f"ERROR: probe {p.get('probe_id', '?')!r} missing keys: {sorted(missing)}")
        if p["target_dim"] not in DIMENSIONS:
            sys.exit(f"ERROR: probe {p['probe_id']!r} has invalid target_dim: {p['target_dim']!r}")
        if p["probe_id"] in seen_ids:
            sys.exit(f"ERROR: duplicate probe_id: {p['probe_id']!r}")
        seen_ids.add(p["probe_id"])
        for dim, band in p.get("expected", {}).items():
            if not (len(band) == 2 and 0.0 <= band[0] <= band[1] <= 1.0):
                sys.exit(f"ERROR: probe {p['probe_id']!r} has an invalid band for {dim}: {band}")
    return probes


def _build_messages(probe: dict) -> list[dict]:
    """Mirror evaluator.score_response's message construction exactly — same
    truncation slices — so calibration measures the production configuration."""
    response_truncated = probe["response_text"][:1500]
    prompt_text = f"Prompt: {probe['prompt_text'][:500]}\n\nResponse: {response_truncated}"
    return [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user",   "content": prompt_text},
    ]


def run_probes(probes: list[dict], *, client=None, tree=None, throttle=None) -> list[dict]:
    """Call the judge REPEATS times per probe. Returns one row dict per (probe, run)."""
    call_kwargs = {}
    if client is not None:
        call_kwargs["client"] = client
    if tree is not None:
        call_kwargs["tree"] = tree
    if throttle is not None:
        call_kwargs["throttle"] = throttle

    rows = []
    for probe in probes:
        dim = probe["target_dim"]
        expect_null = dim in set(probe.get("expect_null", []))
        band = probe.get("expected", {}).get(dim)

        for run_idx in range(REPEATS):
            messages = _build_messages(probe)
            result = call_model(model_id=JUDGE_MODEL, messages=messages, role="judge", **call_kwargs)
            scores, parse_error = parse_judge_json(result.text)
            score = scores[dim]

            if expect_null:
                within_band = math.isnan(score)
                expected_low, expected_high = "", ""
            elif band is not None:
                expected_low, expected_high = band
                within_band = (not math.isnan(score)) and (expected_low <= score <= expected_high)
            else:
                expected_low, expected_high = "", ""
                within_band = False

            # Parse failures ARE reliability failures — never dropped, never
            # silently treated as a band hit even if the NaN happens to satisfy
            # an expect_null check.
            if parse_error is not None:
                within_band = False

            rows.append({
                "probe_id":     probe["probe_id"],
                "target_dim":   dim,
                "run_idx":      run_idx,
                "score":        score,
                "expected_low":  expected_low,
                "expected_high": expected_high,
                "within_band":  within_band,
                "judge_model":  result.model_used,
                "parse_error":  parse_error or "",
            })
    return rows


def aggregate(rows: list[dict]) -> list[dict]:
    """One row per dimension. Rows scored by a fallback judge model are excluded
    from headline stats (a fallback-scored probe measures a different judge) and
    counted separately in n_fallback_scored."""
    summary = []
    for dim in DIMENSIONS:
        dim_rows = [r for r in rows if r["target_dim"] == dim]
        if not dim_rows:
            continue

        primary_rows  = [r for r in dim_rows if r["judge_model"] == JUDGE_MODEL]
        fallback_rows = [r for r in dim_rows if r["judge_model"] != JUDGE_MODEL]

        probe_ids = sorted({r["probe_id"] for r in dim_rows})
        n_runs = len(primary_rows)
        n_parse_failures = sum(1 for r in primary_rows if r["parse_error"])
        hits = sum(1 for r in primary_rows if r["within_band"])
        band_hit_rate = hits / n_runs if n_runs else float("nan")

        # MAE vs band midpoint — never against a point target (the rubric is
        # discrete: 1.00/0.85/0.60/0.30/0.00). Skip null-check rows (no band)
        # and NaN scores (already reflected in band_hit_rate/n_parse_failures).
        abs_errors = []
        for r in primary_rows:
            if r["expected_low"] == "" or r["expected_high"] == "":
                continue
            score = r["score"]
            if isinstance(score, float) and math.isnan(score):
                continue
            midpoint = (r["expected_low"] + r["expected_high"]) / 2
            abs_errors.append(abs(score - midpoint))
        mae = sum(abs_errors) / len(abs_errors) if abs_errors else float("nan")

        # test_retest_std: mean over probes of the std of that probe's REPEATS
        # run scores (NaN runs excluded per-probe; an all-NaN probe contributes
        # NaN and is excluded from the cross-probe mean, matching nanmean
        # convention used throughout leaderboard.py).
        probe_stds = []
        for pid in probe_ids:
            probe_scores = [r["score"] for r in primary_rows if r["probe_id"] == pid]
            valid = [s for s in probe_scores if not (isinstance(s, float) and math.isnan(s))]
            probe_stds.append(statistics.pstdev(valid) if valid else float("nan"))
        valid_stds = [s for s in probe_stds if not math.isnan(s)]
        test_retest_std = sum(valid_stds) / len(valid_stds) if valid_stds else float("nan")

        summary.append({
            "dim":                   dim,
            "n_probes":              len(probe_ids),
            "n_runs":                n_runs,
            "band_hit_rate":         band_hit_rate,
            "mae_vs_band_midpoint":  mae,
            "test_retest_std":       test_retest_std,
            "n_parse_failures":      n_parse_failures,
            "n_fallback_scored":     len(fallback_rows),
        })
    return summary


def _write_csv(path: str, rows: list[dict], fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _make_dry_run_client() -> MagicMock:
    """A mocked OpenAI client returning one fixed valid judge JSON, so the
    runner's parsing/aggregation/CSV-writing path can be exercised offline.
    Pattern mirrors tests/test_fallback.py's _fake_chat_completion."""
    fixed_json = (
        '{"factuality":0.85,"reasoning":0.85,"instruction_following":0.85,'
        '"format_compliance":0.85,"verbosity":0.85}'
    )
    resp = MagicMock()
    msg = MagicMock()
    msg.content = fixed_json
    choice = MagicMock()
    choice.message = msg
    resp.choices = [choice]
    usage = MagicMock()
    usage.total_tokens = 20
    resp.usage = usage

    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return client


def _make_generous_tree() -> HTBTree:
    """Fresh HTB tree with ample tokens/budget so dry-run calls never block on
    real rate limiting or touch the process-global daily counters."""
    tree = HTBTree()
    with tree.lock:
        for n in [tree.root, *tree.providers.values()]:
            n.tokens = 1000.0
            n.daily_remaining = 1000
            n.daily_budget = 1000
    return tree


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Use a mocked judge client + isolated HTB tree; no network access.")
    parser.add_argument("--yes", action="store_true",
                        help="Confirm burning real nvidia judge-model quota (required for a real run).")
    parser.add_argument("--out-dir", default=None,
                        help="Directory to write calibration_runs.csv / judge_calibration.csv. "
                             "Defaults to data/ (real run) or a temp dir (dry run).")
    args = parser.parse_args()

    probes = load_probes()
    total_calls = len(probes) * REPEATS

    if args.dry_run:
        out_dir = args.out_dir or tempfile.mkdtemp(prefix="kriterion_calibration_dryrun_")
        print(f"[dry-run] {len(probes)} probes x {REPEATS} repeats = {total_calls} mocked calls. "
              f"Writing to {out_dir}")
        dry_run_tree = _make_generous_tree()
        rows = run_probes(
            probes,
            client=_make_dry_run_client(),
            tree=dry_run_tree,
            throttle=AdaptiveThrottle(dry_run_tree),
        )
    else:
        print(f"{len(probes)} probes x {REPEATS} repeats = {total_calls} calls "
              f"— uses ~{total_calls} of nvidia's {JUDGE_RPD} RPD judge budget. "
              f"Do not run alongside a main eval pass.")
        if total_calls > JUDGE_RPD:
            sys.exit(f"ERROR: {total_calls} calls exceeds the {JUDGE_RPD} RPD judge budget. Refusing to run.")
        if not args.yes:
            sys.exit("Refusing to run without --yes (this burns real nvidia judge-model quota). "
                      "Re-run with --yes to proceed.")
        out_dir = args.out_dir or DATA_DIR
        rows = run_probes(probes)

    summary = aggregate(rows)

    os.makedirs(out_dir, exist_ok=True)
    runs_path = os.path.join(out_dir, "calibration_runs.csv")
    summary_path = os.path.join(out_dir, "judge_calibration.csv")
    _write_csv(runs_path, rows, RUN_FIELDS)
    _write_csv(summary_path, summary, SUMMARY_FIELDS)

    print(f"Wrote {runs_path} ({len(rows)} rows)")
    print(f"Wrote {summary_path} ({len(summary)} rows)")
    for s in summary:
        print(f"  {s['dim']:<22} band_hit_rate={s['band_hit_rate']:.2f}  "
              f"mae={s['mae_vs_band_midpoint']:.3f}  test_retest_std={s['test_retest_std']:.3f}  "
              f"parse_failures={s['n_parse_failures']}  fallback_scored={s['n_fallback_scored']}")


if __name__ == "__main__":
    main()
