"""Scoring + leaderboard tests. All judge calls are mocked."""
import math
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

import evaluator
from config.llm import CallResult
from leaderboard import (
    bootstrap_ci,
    compute_leaderboard,
    compute_overall_strict_row,
)


def _judge_returning(text: str, *, model="judge-x", latency=10, tokens=5):
    def _fake_call(model_id, messages, role, **_kw):
        return CallResult(
            text=text, latency_ms=latency, tokens_used=tokens, model_used=model,
        )
    return _fake_call


def test_empty_judge_all_four_nan_and_judge_empty_true():
    fake = _judge_returning("")
    with patch.object(evaluator, "call_model", side_effect=fake):
        scores = evaluator.score_response(
            {"id": "X", "prompt_text": "Hi"}, "some response"
        )
    assert scores["judge_empty"] is True
    assert scores["parse_error"] == "Empty judge response"
    for dim in ("factuality", "reasoning", "instruction_following", "format_compliance"):
        assert math.isnan(scores[dim]), f"{dim} should be NaN"
    assert math.isnan(scores["overall_applicable"])


def test_unparseable_judge_all_nan():
    fake = _judge_returning("not valid json {")
    with patch.object(evaluator, "call_model", side_effect=fake):
        scores = evaluator.score_response(
            {"id": "X", "prompt_text": "Hi"}, "resp"
        )
    assert scores["judge_empty"] is True
    assert "JSONDecodeError" in scores["parse_error"]
    for dim in ("factuality", "reasoning", "instruction_following", "format_compliance"):
        assert math.isnan(scores[dim])


def test_overall_applicable_excludes_nan_dims():
    fake = _judge_returning(
        '{"factuality": null, "reasoning": null, '
        '"instruction_following": 0.80, "format_compliance": 0.60}'
    )
    with patch.object(evaluator, "call_model", side_effect=fake):
        scores = evaluator.score_response(
            {"id": "X", "prompt_text": "Hi"}, "resp"
        )
    assert math.isnan(scores["factuality"])
    assert math.isnan(scores["reasoning"])
    assert scores["instruction_following"] == 0.80
    assert scores["format_compliance"] == 0.60
    # nanmean of [nan, nan, 0.80, 0.60] = 0.70
    assert scores["overall_applicable"] == pytest.approx(0.70)


def test_overall_strict_imputes_with_model_mean():
    """Strict overall should impute NaN dims with the model's own dim mean."""
    row = pd.Series({
        "factuality":            float("nan"),
        "reasoning":             0.5,
        "instruction_following": 0.8,
        "format_compliance":     0.6,
    })
    model_means = {
        "factuality":            0.4,   # imputed in for the NaN above
        "reasoning":             0.5,
        "instruction_following": 0.8,
        "format_compliance":     0.6,
    }
    strict = compute_overall_strict_row(row, model_means)
    # mean of [0.4, 0.5, 0.8, 0.6] = 0.575
    assert strict == pytest.approx(0.575)


def test_bootstrap_ci_bounds_are_sane():
    rng = np.random.default_rng(0)
    values = rng.normal(loc=0.7, scale=0.05, size=200)
    lo, hi = bootstrap_ci(values, iters=500, seed=1)
    mean = float(np.mean(values))
    assert lo < mean < hi
    # CI width should be small for n=200 low-variance samples
    assert (hi - lo) < 0.05


def test_bootstrap_ci_handles_all_nan():
    lo, hi = bootstrap_ci(np.array([np.nan, np.nan, np.nan]))
    assert math.isnan(lo) and math.isnan(hi)


def test_leaderboard_overall_strict_vs_applicable():
    """Build a tiny synthetic df: model M1 has 2 rows, one with a NaN dim.
    overall_applicable averages only present dims per row.
    overall_strict imputes the NaN with M1's own mean for that dim."""
    df = pd.DataFrame([
        {"model": "M1", "prompt_id": "p1",
         "factuality": 1.0, "reasoning": 0.5,
         "instruction_following": 0.8, "format_compliance": 0.7,
         "overall_applicable": float(np.nanmean([1.0, 0.5, 0.8, 0.7])),
         "latency_ms": 100, "tokens_used": 50},
        {"model": "M1", "prompt_id": "p2",
         "factuality": float("nan"), "reasoning": 0.7,
         "instruction_following": 0.9, "format_compliance": 0.8,
         "overall_applicable": float(np.nanmean([np.nan, 0.7, 0.9, 0.8])),
         "latency_ms": 200, "tokens_used": 60},
    ])
    lb = compute_leaderboard(df)
    row = lb.iloc[0]
    # Model dim means: factuality=1.0 (only p1 had it), reasoning=0.6, IF=0.85, FC=0.75
    # Strict row 1: mean(1.0, 0.5, 0.8, 0.7) = 0.75
    # Strict row 2 (impute factuality=1.0): mean(1.0, 0.7, 0.9, 0.8) = 0.85
    # overall_strict = mean(0.75, 0.85) = 0.80
    assert row["overall_strict"] == pytest.approx(0.80, abs=1e-3)
    # CI columns exist and are populated.
    assert row["ci_low"] is not None
    assert row["ci_high"] is not None
    assert row["ci_low"] <= row["overall_applicable"] <= row["ci_high"]
