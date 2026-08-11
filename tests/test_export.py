"""Per-prompt results export tests. No network, no real prompt_suite.json dependency."""
import json
import math

import pandas as pd
import pytest

from leaderboard import export_by_prompt, DIMENSIONS, HEADLINE_DIMS


def _write_suite(tmp_path, prompts):
    path = tmp_path / "prompt_suite.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prompts, f)
    return str(path)


def _base_row(prompt_id, model, **overrides):
    row = {
        "prompt_id": prompt_id,
        "model": model,
        "factuality": 0.8,
        "reasoning": 0.7,
        "instruction_following": 0.9,
        "format_compliance": 0.0,   # deliberately bad — must not affect overall
        "verbosity": 0.6,
        "judge_empty": False,
        "fallback_triggered": False,
        "latency_ms": 100,
        "difficulty": "easy",
    }
    row.update(overrides)
    return row


def test_row_count_matches_input():
    suite_prompts = [
        {"id": "P1", "category": "factual_recall", "difficulty": "easy"},
        {"id": "P2", "category": "code_generation", "difficulty": "hard"},
    ]
    df = pd.DataFrame([
        _base_row("P1", "model-a"),
        _base_row("P1", "model-b"),
        _base_row("P2", "model-a"),
    ])
    out = export_by_prompt(df, prompts_path="does_not_matter")
    assert len(out) == 3
    del suite_prompts  # unused here; category join covered separately


def test_category_join_from_suite(tmp_path):
    suite_path = _write_suite(tmp_path, [
        {"id": "P1", "category": "factual_recall", "difficulty": "easy"},
        {"id": "P2", "category": "code_generation", "difficulty": "hard"},
    ])
    df = pd.DataFrame([
        _base_row("P1", "model-a"),
        _base_row("P2", "model-a"),
    ])
    out = export_by_prompt(df, prompts_path=suite_path)
    cats = dict(zip(out["prompt_id"], out["category"]))
    assert cats == {"P1": "factual_recall", "P2": "code_generation"}


def test_nan_dim_serializes_as_empty_cell_not_zero_or_string(tmp_path):
    suite_path = _write_suite(tmp_path, [
        {"id": "P1", "category": "code_generation", "difficulty": "easy"},
    ])
    df = pd.DataFrame([
        _base_row("P1", "model-a", factuality=float("nan")),
    ])
    out = export_by_prompt(df, prompts_path=suite_path)
    assert math.isnan(out.loc[0, "factuality"])

    csv_text = out.to_csv(index=False)
    assert "nan" not in csv_text.lower()
    # header,P1,code_generation,easy,model-a,<empty factuality>,...
    factuality_cell = csv_text.splitlines()[1].split(",")[4]
    assert factuality_cell == ""


def test_unknown_prompt_id_warns_and_does_not_crash(tmp_path, capsys):
    suite_path = _write_suite(tmp_path, [
        {"id": "P1", "category": "factual_recall", "difficulty": "easy"},
    ])
    df = pd.DataFrame([
        _base_row("P1", "model-a"),
        _base_row("GHOST_001", "model-a"),
    ])
    out = export_by_prompt(df, prompts_path=suite_path)
    assert len(out) == 2  # not dropped
    ghost_row = out[out["prompt_id"] == "GHOST_001"].iloc[0]
    assert ghost_row["category"] == "unknown"
    captured = capsys.readouterr()
    assert "GHOST_001" in captured.out
    assert "WARNING" in captured.out


def test_overall_applicable_row_uses_headline_dims_only(tmp_path):
    suite_path = _write_suite(tmp_path, [
        {"id": "P1", "category": "factual_recall", "difficulty": "easy"},
    ])
    # format_compliance = 0.0 must not drag overall_applicable_row down —
    # it is excluded from HEADLINE_DIMS.
    df = pd.DataFrame([
        _base_row(
            "P1", "model-a",
            factuality=1.0, reasoning=1.0, instruction_following=1.0,
            format_compliance=0.0, verbosity=1.0,
        ),
    ])
    out = export_by_prompt(df, prompts_path=suite_path)
    assert set(HEADLINE_DIMS) == {"factuality", "reasoning", "instruction_following", "verbosity"}
    assert out.loc[0, "overall_applicable_row"] == pytest.approx(1.0)


def test_output_columns_match_spec(tmp_path):
    suite_path = _write_suite(tmp_path, [
        {"id": "P1", "category": "factual_recall", "difficulty": "easy"},
    ])
    df = pd.DataFrame([_base_row("P1", "model-a")])
    out = export_by_prompt(df, prompts_path=suite_path)
    expected = (
        ["prompt_id", "category", "difficulty", "model"]
        + DIMENSIONS
        + ["overall_applicable_row", "judge_empty", "fallback_triggered", "latency_ms"]
    )
    assert list(out.columns) == expected
