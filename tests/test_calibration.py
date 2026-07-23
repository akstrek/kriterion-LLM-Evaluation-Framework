"""Judge calibration probe tests. All judge calls are mocked — zero network access."""
import math
from unittest.mock import MagicMock

import pytest

import calibration_probes
from calibration_probes import aggregate, load_probes, run_probes
from config.llm import AdaptiveThrottle
from evaluator import parse_judge_json


# ── parse_judge_json round-trip (pins the shared parser extracted from evaluator.py) ──


def test_parse_judge_json_valid():
    scores, err = parse_judge_json(
        '{"factuality":1.0,"reasoning":0.85,"instruction_following":0.6,'
        '"format_compliance":0.3,"verbosity":0.0}'
    )
    assert err is None
    assert scores == {
        "factuality": 1.0, "reasoning": 0.85, "instruction_following": 0.6,
        "format_compliance": 0.3, "verbosity": 0.0,
    }


def test_parse_judge_json_fenced():
    scores, err = parse_judge_json(
        '```json\n{"factuality":1.0,"reasoning":0.85,"instruction_following":0.6,'
        '"format_compliance":0.3,"verbosity":0.0}\n```'
    )
    assert err is None
    assert scores["factuality"] == 1.0


def test_parse_judge_json_null_dims_become_nan():
    scores, err = parse_judge_json(
        '{"factuality":null,"reasoning":null,"instruction_following":0.5,'
        '"format_compliance":0.5,"verbosity":0.5}'
    )
    assert err is None
    assert math.isnan(scores["factuality"])
    assert math.isnan(scores["reasoning"])
    assert scores["instruction_following"] == 0.5


def test_parse_judge_json_empty_string():
    scores, err = parse_judge_json("")
    assert err == "Empty judge response"
    for v in scores.values():
        assert math.isnan(v)


def test_parse_judge_json_garbage():
    scores, err = parse_judge_json("not valid json {")
    assert err.startswith("JSONDecodeError")
    for v in scores.values():
        assert math.isnan(v)


# ── probe-suite validation ────────────────────────────────────────────────────


def test_real_probe_suite_shape():
    probes = load_probes()
    assert len(probes) == 32

    ids = [p["probe_id"] for p in probes]
    assert len(ids) == len(set(ids)), "duplicate probe_id"

    for p in probes:
        assert p["target_dim"] in calibration_probes.DIMENSIONS
        for dim, band in p.get("expected", {}).items():
            assert len(band) == 2
            assert 0.0 <= band[0] <= band[1] <= 1.0

    null_check_probes = [p for p in probes if "expect_null" in p]
    assert len(null_check_probes) == 2


# ── runner aggregation ────────────────────────────────────────────────────────


def _isolated_tree():
    from config.llm import HTBTree
    tree = HTBTree()
    with tree.lock:
        for n in [tree.root, *tree.providers.values()]:
            n.tokens = 1000.0
            n.daily_remaining = 1000
            n.daily_budget = 1000
    return tree


def _fake_completion(text: str, tokens: int = 10):
    resp = MagicMock()
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp.choices = [choice]
    usage = MagicMock()
    usage.total_tokens = tokens
    resp.usage = usage
    return resp


def _probe(probe_id, target_dim, band):
    return {
        "probe_id": probe_id,
        "target_dim": target_dim,
        "prompt_text": "irrelevant prompt",
        "response_text": "irrelevant response",
        "expected": {target_dim: band},
        "applicable_dims": [target_dim],
        "rationale": "test fixture",
    }


def test_runner_aggregation_band_hits_and_parse_failures():
    """One in-band run, one out-of-band run, one unparseable run."""
    probe = _probe("TEST_VERB_1", "verbosity", [0.85, 1.00])

    responses = [
        _fake_completion(
            '{"factuality":null,"reasoning":null,"instruction_following":0.5,'
            '"format_compliance":0.5,"verbosity":0.85}'
        ),
        _fake_completion(
            '{"factuality":null,"reasoning":null,"instruction_following":0.5,'
            '"format_compliance":0.5,"verbosity":0.30}'
        ),
        _fake_completion("not valid json {"),
    ]
    client = MagicMock()
    client.chat.completions.create.side_effect = responses

    tree = _isolated_tree()
    throttle = AdaptiveThrottle(tree)

    rows = run_probes([probe], client=client, tree=tree, throttle=throttle)
    assert len(rows) == 3
    assert rows[0]["within_band"] is True
    assert rows[1]["within_band"] is False
    assert rows[1]["parse_error"] == ""
    assert rows[2]["within_band"] is False
    assert rows[2]["parse_error"] != ""

    summary = aggregate(rows)
    row = next(s for s in summary if s["dim"] == "verbosity")
    assert row["n_runs"] == 3
    assert row["n_parse_failures"] == 1
    assert row["band_hit_rate"] == pytest.approx(1 / 3)
    assert row["n_fallback_scored"] == 0


def test_test_retest_std_excludes_all_nan_probes():
    """A probe whose 3 runs are all unparseable contributes NaN to test_retest_std
    and must not poison the dimension-level mean across probes."""
    probe_nan = _probe("TEST_REAS_NAN", "reasoning", [0.85, 1.00])
    probe_clean = _probe("TEST_REAS_CLEAN", "reasoning", [0.85, 1.00])

    unparseable = [_fake_completion("garbage {{{") for _ in range(3)]
    clean = [
        _fake_completion(
            '{"factuality":null,"reasoning":0.85,"instruction_following":0.5,'
            '"format_compliance":0.5,"verbosity":0.5}'
        )
        for _ in range(3)
    ]
    client = MagicMock()
    client.chat.completions.create.side_effect = unparseable + clean

    tree = _isolated_tree()
    throttle = AdaptiveThrottle(tree)

    rows = run_probes([probe_nan, probe_clean], client=client, tree=tree, throttle=throttle)
    summary = aggregate(rows)
    row = next(s for s in summary if s["dim"] == "reasoning")

    assert row["n_parse_failures"] == 3
    assert row["test_retest_std"] == pytest.approx(0.0)  # only probe_clean contributes; its 3 runs are identical
    assert row["band_hit_rate"] == pytest.approx(3 / 6)  # 3 clean hits out of 6 total runs


def test_expect_null_probe_hits_band_only_on_actual_null():
    probe = _probe("TEST_NULL", "factuality", [])
    probe["expected"] = {}
    probe["expect_null"] = ["factuality"]

    responses = [
        _fake_completion(
            '{"factuality":null,"reasoning":null,"instruction_following":0.5,'
            '"format_compliance":0.5,"verbosity":0.5}'
        ),
        _fake_completion(
            '{"factuality":0.5,"reasoning":null,"instruction_following":0.5,'
            '"format_compliance":0.5,"verbosity":0.5}'
        ),
        _fake_completion(""),
    ]
    client = MagicMock()
    client.chat.completions.create.side_effect = responses

    tree = _isolated_tree()
    throttle = AdaptiveThrottle(tree)

    rows = run_probes([probe], client=client, tree=tree, throttle=throttle)
    assert rows[0]["within_band"] is True    # actual null -> correct
    assert rows[1]["within_band"] is False   # judge wrongly returned a number
    assert rows[2]["within_band"] is False   # NaN via parse failure, not a real null -> still a failure
