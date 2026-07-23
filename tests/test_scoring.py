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
    HEADLINE_DIMS,
)


def _judge_returning(text: str, *, model="judge-x", latency=10, tokens=5):
    def _fake_call(model_id, messages, role, **_kw):
        return CallResult(
            text=text, latency_ms=latency, tokens_used=tokens, model_used=model,
        )
    return _fake_call


# ── score_response: parse-only contract (no headline computation here) ───────

ALL_DIMS = ("factuality", "reasoning", "instruction_following", "format_compliance", "verbosity")


def test_empty_judge_all_five_nan_and_judge_empty_true():
    fake = _judge_returning("")
    with patch.object(evaluator, "call_model", side_effect=fake):
        scores = evaluator.score_response(
            {"id": "X", "prompt_text": "Hi"}, "some response"
        )
    assert scores["judge_empty"] is True
    assert scores["parse_error"] == "Empty judge response"
    for dim in ALL_DIMS:
        assert math.isnan(scores[dim]), f"{dim} should be NaN"
    # Headline policy lives in leaderboard.py, not in score_response.
    assert "overall_applicable" not in scores


def test_unparseable_judge_all_nan():
    fake = _judge_returning("not valid json {")
    with patch.object(evaluator, "call_model", side_effect=fake):
        scores = evaluator.score_response(
            {"id": "X", "prompt_text": "Hi"}, "resp"
        )
    assert scores["judge_empty"] is True
    assert "JSONDecodeError" in scores["parse_error"]
    for dim in ALL_DIMS:
        assert math.isnan(scores[dim])


def test_grounded_message_includes_reference_when_ground_truth_present():
    """Reference line appears iff ground_truth is non-empty; Reference precedes Response."""
    captured = {}

    def _fake_call(model_id, messages, role, **_kw):
        captured["user_msg"] = messages[1]["content"]
        return CallResult(text="{}", latency_ms=1, tokens_used=1, model_used="judge-x")

    with patch.object(evaluator, "call_model", side_effect=_fake_call):
        scores = evaluator.score_response(
            {"id": "FR_001", "prompt_text": "What is the atomic number of gold?",
             "ground_truth": "Na"},
            "resp",
        )
    msg = captured["user_msg"]
    assert "Reference" in msg
    assert msg.index("Reference") < msg.index("Response:")
    assert msg.strip().endswith("Response: resp")
    assert scores["gt_provided"] is True


def test_grounded_message_omits_reference_when_ground_truth_absent_or_empty():
    for prompt_obj in (
        {"id": "X", "prompt_text": "Hi"},
        {"id": "X", "prompt_text": "Hi", "ground_truth": ""},
        {"id": "X", "prompt_text": "Hi", "ground_truth": "   "},
    ):
        captured = {}

        def _fake_call(model_id, messages, role, **_kw):
            captured["user_msg"] = messages[1]["content"]
            return CallResult(text="{}", latency_ms=1, tokens_used=1, model_used="judge-x")

        with patch.object(evaluator, "call_model", side_effect=_fake_call):
            scores = evaluator.score_response(prompt_obj, "resp")
        assert "Reference" not in captured["user_msg"]
        assert scores["gt_provided"] is False


def test_response_truncated_flag_and_named_constants():
    long_response = "x" * (evaluator.JUDGE_RESPONSE_MAX_CHARS + 100)
    captured = {}

    def _fake_call(model_id, messages, role, **_kw):
        captured["user_msg"] = messages[1]["content"]
        return CallResult(text="{}", latency_ms=1, tokens_used=1, model_used="judge-x")

    with patch.object(evaluator, "call_model", side_effect=_fake_call):
        scores = evaluator.score_response({"id": "X", "prompt_text": "Hi"}, long_response)

    assert scores["response_truncated"] is True
    # The judge message's Response segment is capped at JUDGE_RESPONSE_MAX_CHARS,
    # not the full over-length response.
    response_segment = captured["user_msg"].split("Response: ", 1)[1]
    assert len(response_segment) == evaluator.JUDGE_RESPONSE_MAX_CHARS

    short_response = "y" * 10
    with patch.object(evaluator, "call_model", side_effect=_fake_call):
        scores_short = evaluator.score_response({"id": "X", "prompt_text": "Hi"}, short_response)
    assert scores_short["response_truncated"] is False


def test_score_response_parses_all_five_dims():
    fake = _judge_returning(
        '{"factuality": null, "reasoning": null, '
        '"instruction_following": 0.80, "format_compliance": 0.60, '
        '"verbosity": 0.72}'
    )
    with patch.object(evaluator, "call_model", side_effect=fake):
        scores = evaluator.score_response(
            {"id": "X", "prompt_text": "Hi"}, "resp"
        )
    assert math.isnan(scores["factuality"])
    assert math.isnan(scores["reasoning"])
    assert scores["instruction_following"] == 0.80
    assert scores["format_compliance"] == 0.60
    assert scores["verbosity"] == 0.72
    # No overall_applicable returned — that lives in leaderboard.py now.
    assert "overall_applicable" not in scores


# ── leaderboard headline policy ──────────────────────────────────────────────


def test_headline_dims_exclude_format_compliance():
    """The headline policy is a 4-dim mean that explicitly excludes format_compliance."""
    assert set(HEADLINE_DIMS) == {"factuality", "reasoning", "instruction_following", "verbosity"}
    assert "format_compliance" not in HEADLINE_DIMS


def test_overall_strict_imputes_headline_nan_with_model_mean():
    """compute_overall_strict_row should impute NaN HEADLINE dims with the model's own dim mean."""
    row = pd.Series({
        "factuality":            float("nan"),
        "reasoning":             0.5,
        "instruction_following": 0.8,
        "format_compliance":     0.6,   # not in headline; ignored by strict
        "verbosity":             0.7,
    })
    model_means = {
        "factuality":            0.4,   # imputed in for the NaN above
        "reasoning":             0.5,
        "instruction_following": 0.8,
        "format_compliance":     0.6,
        "verbosity":             0.7,
    }
    strict = compute_overall_strict_row(row, model_means)
    # mean of [0.4, 0.5, 0.8, 0.7] = 0.6 (format_compliance NOT included)
    assert strict == pytest.approx(0.6)


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


def test_leaderboard_headline_uses_four_dims_not_five():
    """overall_applicable must be the mean of HEADLINE_DIMS only — format_compliance
    is reported as avg_format_compliance but NOT in the headline."""
    df = pd.DataFrame([
        {"model": "M1", "prompt_id": "p1",
         "factuality": 1.0, "reasoning": 0.5,
         "instruction_following": 0.8, "format_compliance": 0.2,
         "verbosity": 0.9, "latency_ms": 100, "tokens_used": 50},
        {"model": "M1", "prompt_id": "p2",
         "factuality": 0.8, "reasoning": 0.7,
         "instruction_following": 0.9, "format_compliance": 0.1,
         "verbosity": 0.7, "latency_ms": 200, "tokens_used": 60},
    ])
    lb = compute_leaderboard(df)
    row = lb.iloc[0]
    # Row p1 headline mean: mean(1.0, 0.5, 0.8, 0.9) = 0.80
    # Row p2 headline mean: mean(0.8, 0.7, 0.9, 0.7) = 0.775
    # overall_applicable = mean(0.80, 0.775) = 0.7875
    assert row["overall_applicable"] == pytest.approx(0.7875, abs=1e-3)
    # avg_format_compliance is still reported.
    assert row["avg_format_compliance"] == pytest.approx(0.15, abs=1e-3)
    # 5-dim mean (which we are NOT computing) would be different — sanity check.
    five_dim = float(np.mean([
        np.mean([1.0, 0.5, 0.8, 0.2, 0.9]),
        np.mean([0.8, 0.7, 0.9, 0.1, 0.7]),
    ]))
    assert abs(row["overall_applicable"] - five_dim) > 0.01
