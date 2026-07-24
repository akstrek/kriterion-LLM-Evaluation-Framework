"""second_judge.py tests. All judge calls are mocked — zero network access."""
from unittest.mock import MagicMock

import pandas as pd
import pytest

import second_judge
from config.llm import AdaptiveThrottle, HTBTree, JUDGE2_MODEL, JUDGE_SYSTEM_PROMPT, call_model
from evaluator import build_judge_user_message
from second_judge import (
    aggregate_agreement,
    load_completed_judge2_pairs,
    load_v2_results,
    run_second_judge,
    sample_pairs,
    score_pair_with_judge2,
    write_agreement_csv,
)


# ── Deterministic sampling ────────────────────────────────────────────────────


def _synthetic_universe(n_prompts=600, models=("m1", "m2", "m3")):
    return [(f"P{i:04d}", m) for i in range(n_prompts) for m in models]


def test_sample_pairs_selects_exactly_300_of_1800_100_per_model():
    pairs = _synthetic_universe()
    sampled = sample_pairs(pairs)
    assert len(sampled) == 300
    counts = {}
    for _, model in sampled:
        counts[model] = counts.get(model, 0) + 1
    assert counts == {"m1": 100, "m2": 100, "m3": 100}


def test_sample_pairs_byte_identical_across_invocations():
    pairs = _synthetic_universe()
    s1 = sample_pairs(pairs)
    s2 = sample_pairs(pairs)
    assert s1 == s2


def test_sample_pairs_stable_when_unrelated_pair_changes():
    """Changing an unrelated pair's prompt_id (a different model's row) must
    not reshuffle another model's selection — each model's sample depends
    only on its own pairs' hashes."""
    pairs = _synthetic_universe()
    baseline = sample_pairs(pairs)
    baseline_m1 = [p for p in baseline if p[1] == "m1"]

    mutated = [(pid, m) for pid, m in pairs if not (m == "m2" and pid == "P0000")]
    mutated.append(("P9999_REPLACEMENT", "m2"))
    mutated_sample = sample_pairs(mutated)
    mutated_m1 = [p for p in mutated_sample if p[1] == "m1"]

    assert baseline_m1 == mutated_m1


def test_sample_pairs_truncates_when_selection_exceeds_target():
    # A tiny mod so far more than per_model pairs qualify, forcing truncation.
    pairs = [(f"P{i:04d}", "solo") for i in range(600)]
    sampled = sample_pairs(pairs, per_model=100, mod=2)
    assert len(sampled) == 100


def test_sample_pairs_extends_when_selection_is_short():
    # A huge mod so almost nothing qualifies naturally, forcing extension.
    pairs = [(f"P{i:04d}", "solo") for i in range(600)]
    sampled = sample_pairs(pairs, per_model=100, mod=100_000)
    assert len(sampled) == 100


# ── Schema-v2 guard ────────────────────────────────────────────────────────────

_V1_COLUMNS = ["prompt_id", "model", "factuality", "reasoning", "instruction_following",
               "format_compliance", "verbosity", "latency_ms"]


def test_load_v2_results_exits_on_v1_parquet(tmp_path):
    path = tmp_path / "eval_results.parquet"
    df = pd.DataFrame([{"prompt_id": "P1", "model": "m1", "factuality": 0.5, "reasoning": 0.5,
                         "instruction_following": 0.5, "format_compliance": 0.5, "verbosity": 0.5,
                         "latency_ms": 100}])
    df.to_parquet(path)
    with pytest.raises(SystemExit, match="schema-v2"):
        load_v2_results(str(path))


def test_load_v2_results_exits_on_missing_file(tmp_path):
    with pytest.raises(SystemExit, match="schema-v2"):
        load_v2_results(str(tmp_path / "does_not_exist.parquet"))


def test_load_v2_results_exits_on_mixed_rubric_versions(tmp_path):
    path = tmp_path / "eval_results.parquet"
    df = pd.DataFrame([
        {"prompt_id": "P1", "model": "m1", "response_text": "a", "rubric_version": 2},
        {"prompt_id": "P2", "model": "m1", "response_text": "b", "rubric_version": 3},
    ])
    df.to_parquet(path)
    with pytest.raises(SystemExit, match="mixes rubric_version"):
        load_v2_results(str(path))


def test_load_v2_results_passes_on_v2_parquet(tmp_path):
    path = tmp_path / "eval_results.parquet"
    df = pd.DataFrame([
        {"prompt_id": "P1", "model": "m1", "response_text": "a", "rubric_version": 2},
    ])
    df.to_parquet(path)
    loaded = load_v2_results(str(path))
    assert len(loaded) == 1


# ── Message parity: second_judge must send judge 1's exact input ────────────


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


def _isolated_tree():
    """Fresh HTB tree with ample tokens/burst/budget so tests never block on
    real rate limiting. `burst` must be raised too, not just `tokens` — once
    any real wall-clock time elapses between calls (e.g. this test's row
    writes do real fsync I/O), HTBNode.refill() reclamps tokens down to
    `burst`, and the production default (2.0) would make a 4th+ call in a
    test genuinely sleep for 1/rate_per_sec seconds."""
    tree = HTBTree()
    with tree.lock:
        for n in [tree.root, *tree.providers.values()]:
            n.tokens = 1000.0
            n.burst = 1000.0
            n.daily_remaining = 1000
            n.daily_budget = 1000
    return tree


VALID_JUDGE_JSON = (
    '{"factuality":0.85,"reasoning":0.85,"instruction_following":0.85,'
    '"format_compliance":0.85,"verbosity":0.85}'
)


def test_second_judge_system_prompt_matches_judge1():
    """Both judges must be given the identical rubric/system prompt — otherwise
    disagreement measures a different task, not judge bias."""
    prompt_obj = {"id": "P1", "prompt_text": "What is the capital of France?",
                  "ground_truth": "Paris"}
    response_text = "The capital of France is Paris."
    captured = {}

    client = MagicMock()

    def create(model, messages, **_kw):
        captured["messages"] = messages
        return _fake_completion(VALID_JUDGE_JSON)

    client.chat.completions.create.side_effect = create
    tree = _isolated_tree()
    score_pair_with_judge2(prompt_obj, response_text, client=client, tree=tree,
                           throttle=AdaptiveThrottle(tree))

    assert captured["messages"][0]["content"] == JUDGE_SYSTEM_PROMPT
    assert "Paris" in captured["messages"][1]["content"]


def test_build_judge_user_message_used_directly_by_both_paths():
    """Lower-level guarantee: the exact string second_judge builds equals
    what build_judge_user_message returns for the same inputs judge 1 uses."""
    prompt_obj = {"id": "P2", "prompt_text": "Explain photosynthesis.", "ground_truth": ""}
    response_text = "Photosynthesis converts light into chemical energy."
    expected_msg, _ = build_judge_user_message(prompt_obj, response_text)

    client = MagicMock()
    captured = {}

    def create(model, messages, **_kw):
        captured["messages"] = messages
        return _fake_completion(VALID_JUDGE_JSON)

    client.chat.completions.create.side_effect = create
    tree = _isolated_tree()
    score_pair_with_judge2(prompt_obj, response_text, client=client, tree=tree,
                           throttle=AdaptiveThrottle(tree))
    assert captured["messages"][1]["content"] == expected_msg


# ── HTB: judge2 debits poolside, not nvidia ──────────────────────────────────


def test_judge2_role_debits_poolside_not_nvidia():
    tree = _isolated_tree()
    throttle = AdaptiveThrottle(tree)
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_completion(VALID_JUDGE_JSON)

    result = call_model(
        JUDGE2_MODEL, [{"role": "user", "content": "hi"}],
        role="judge2", tree=tree, throttle=throttle, client=client,
    )
    assert result.model_used == JUDGE2_MODEL

    poolside_used = 1000 - tree.providers["poolside"].daily_remaining
    nvidia_used = 1000 - tree.providers["nvidia"].daily_remaining
    assert poolside_used == 1
    assert nvidia_used == 0


def test_call_model_accepts_judge2_role():
    tree = _isolated_tree()
    throttle = AdaptiveThrottle(tree)
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_completion("{}")
    # Should not raise ValueError on role validation.
    call_model(JUDGE2_MODEL, [{"role": "user", "content": "hi"}],
               role="judge2", tree=tree, throttle=throttle, client=client)


# ── Row checkpointing + resume ────────────────────────────────────────────────


def test_run_second_judge_checkpoints_and_resumes(tmp_path):
    rows_dir = str(tmp_path / "judge2_rows")
    pairs = [("P1", "m1"), ("P2", "m1"), ("P3", "m1"), ("P4", "m1")]
    prompts_by_id = {
        pid: {"id": pid, "prompt_text": f"prompt {pid}", "ground_truth": ""}
        for pid, _ in pairs
    }
    response_by_pair = {(pid, m): f"response to {pid}" for pid, m in pairs}

    client = MagicMock()
    client.chat.completions.create.return_value = _fake_completion(VALID_JUDGE_JSON)
    tree = _isolated_tree()

    n_scored = run_second_judge(pairs, prompts_by_id, response_by_pair,
                                 client=client, tree=tree, throttle=AdaptiveThrottle(tree),
                                 rows_dir=rows_dir)
    assert n_scored == 4
    assert load_completed_judge2_pairs(rows_dir) == set(pairs)

    # Resume: half already exist (simulate by removing two files then re-running
    # over the full pair list) — only the missing ones get (re-)scored.
    import os
    from second_judge import _row2_path
    os.remove(_row2_path("P3", "m1", rows_dir))
    os.remove(_row2_path("P4", "m1", rows_dir))

    client2 = MagicMock()
    client2.chat.completions.create.return_value = _fake_completion(VALID_JUDGE_JSON)
    n_scored_2 = run_second_judge(pairs, prompts_by_id, response_by_pair,
                                   client=client2, tree=_isolated_tree(),
                                   throttle=AdaptiveThrottle(_isolated_tree()),
                                   rows_dir=rows_dir)
    assert n_scored_2 == 2
    assert load_completed_judge2_pairs(rows_dir) == set(pairs)


# ── Agreement aggregation ──────────────────────────────────────────────────────


def _judge1_df(rows):
    return pd.DataFrame(rows)


def _judge2_df(rows):
    return pd.DataFrame(rows)


def test_aggregate_agreement_shape_six_rows():
    judge1 = _judge1_df([
        {"prompt_id": "P1", "model": "m1", "factuality": 0.85, "reasoning": 0.6,
         "instruction_following": 0.85, "format_compliance": 0.85, "verbosity": 0.6},
        {"prompt_id": "P2", "model": "m1", "factuality": 0.6, "reasoning": 0.85,
         "instruction_following": 0.6, "format_compliance": 0.6, "verbosity": 0.85},
    ])
    judge2 = _judge2_df([
        {"prompt_id": "P1", "model": "m1", "factuality2": 0.85, "reasoning2": 0.6,
         "instruction_following2": 0.85, "format_compliance2": 0.85, "verbosity2": 0.6,
         "judge2_model": JUDGE2_MODEL, "judge2_empty": False, "parse_error2": "",
         "judge2_latency_ms": 100},
        {"prompt_id": "P2", "model": "m1", "factuality2": 0.6, "reasoning2": 0.85,
         "instruction_following2": 0.6, "format_compliance2": 0.6, "verbosity2": 0.85,
         "judge2_model": JUDGE2_MODEL, "judge2_empty": False, "parse_error2": "",
         "judge2_latency_ms": 100},
    ])
    rows = aggregate_agreement(judge1, judge2)
    assert len(rows) == 6
    dims = {r["dim"] for r in rows}
    assert dims == {"factuality", "reasoning", "instruction_following",
                     "format_compliance", "verbosity", "overall"}


def test_agreement_stats_hand_built_pearson_and_mae():
    judge1 = pd.Series([1.0, 0.85, 0.6, 0.3, 0.0])
    judge2 = pd.Series([0.85, 0.85, 0.6, 0.3, 0.15])
    is_fallback = pd.Series([False] * 5)

    stats = second_judge._agreement_stats(judge1, judge2, is_fallback)
    assert stats["n"] == 5
    expected_mae = sum(abs(a - b) for a, b in zip(judge1, judge2)) / 5
    assert stats["mae"] == pytest.approx(expected_mae)
    assert stats["pearson_r"] != ""
    assert -1.0 <= stats["pearson_r"] <= 1.0
    assert stats["n_judge1_nan_judge2_val"] == 0
    assert stats["n_judge2_nan_judge1_val"] == 0
    assert stats["n_fallback_scored"] == 0


def test_agreement_stats_nan_mismatch_excluded_from_mae_not_counted_as_disagreement():
    """judge1=NaN, judge2=0.85 must land in n_judge1_nan_judge2_val, never in mae/pearson."""
    judge1 = pd.Series([1.0, 0.85, float("nan"), 0.3])
    judge2 = pd.Series([1.0, 0.85, 0.85, 0.3])
    is_fallback = pd.Series([False] * 4)

    stats = second_judge._agreement_stats(judge1, judge2, is_fallback)
    assert stats["n"] == 3  # the NaN row excluded from n
    assert stats["n_judge1_nan_judge2_val"] == 1
    assert stats["n_judge2_nan_judge1_val"] == 0
    assert stats["mae"] == pytest.approx(0.0)


def test_agreement_stats_zero_variance_emits_empty_pearson():
    judge1 = pd.Series([0.85, 0.85, 0.85])
    judge2 = pd.Series([0.85, 0.85, 0.85])
    is_fallback = pd.Series([False] * 3)
    stats = second_judge._agreement_stats(judge1, judge2, is_fallback)
    assert stats["pearson_r"] == ""
    assert stats["mae"] == pytest.approx(0.0)


def test_agreement_stats_fallback_scored_excluded_from_headline_and_counted():
    judge1 = pd.Series([0.85, 0.6, 0.3])
    judge2 = pd.Series([0.85, 0.9, 0.3])
    is_fallback = pd.Series([False, True, False])
    stats = second_judge._agreement_stats(judge1, judge2, is_fallback)
    assert stats["n"] == 2          # the fallback-scored row excluded
    assert stats["n_fallback_scored"] == 1
    assert stats["mae"] == pytest.approx(0.0)  # only the two agreeing rows counted


# ── End-to-end: synthetic 18-row v2 fixture through the full pipeline ────────


def test_full_pipeline_18_row_v2_fixture(tmp_path):
    """Acceptance criterion 3: schema-v2 fixture -> deterministic sample ->
    checkpointed judge2 calls -> resume with half pre-existing -> 6-row
    judge_agreement.csv with all documented columns."""
    models = ["m1", "m2", "m3"]
    prompt_ids = [f"P{i:03d}" for i in range(6)]

    fixture_rows = []
    for pid in prompt_ids:
        for model in models:
            fixture_rows.append({
                "prompt_id": pid, "model": model,
                "factuality": 0.85, "reasoning": 0.6, "instruction_following": 0.85,
                "format_compliance": 0.85, "verbosity": 0.6,
                "response_text": f"response for {pid} by {model}",
                "rubric_version": 2, "difficulty": "easy",
            })
    assert len(fixture_rows) == 18
    parquet_path = tmp_path / "eval_results.parquet"
    pd.DataFrame(fixture_rows).to_parquet(parquet_path)

    df1 = load_v2_results(str(parquet_path))
    assert len(df1) == 18

    prompts_by_id = {
        pid: {"id": pid, "prompt_text": f"prompt text {pid}", "ground_truth": "some fact"}
        for pid in prompt_ids
    }
    response_by_pair = {
        (r["prompt_id"], r["model"]): r["response_text"] for r in fixture_rows
    }

    universe = list(zip(df1["prompt_id"], df1["model"]))
    sampled = sample_pairs(universe)
    # Only 6 pairs exist per model — fewer than PER_MODEL_TARGET=100 — so the
    # extend step pulls in every available pair for each model.
    assert len(sampled) == 18
    assert sample_pairs(universe) == sampled  # deterministic across invocations

    rows_dir = str(tmp_path / "judge2_rows")
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_completion(VALID_JUDGE_JSON)
    tree = _isolated_tree()
    n_scored = run_second_judge(sampled, prompts_by_id, response_by_pair,
                                 client=client, tree=tree, throttle=AdaptiveThrottle(tree),
                                 rows_dir=rows_dir)
    assert n_scored == 18
    assert load_completed_judge2_pairs(rows_dir) == set(sampled)

    # Resume: drop half the checkpointed rows, re-run over the full sample —
    # only the missing half should be (re-)scored.
    import os
    from second_judge import _row2_path
    half = sampled[:9]
    for pid, model in half:
        os.remove(_row2_path(pid, model, rows_dir))

    client2 = MagicMock()
    client2.chat.completions.create.return_value = _fake_completion(VALID_JUDGE_JSON)
    tree2 = _isolated_tree()
    n_scored_resume = run_second_judge(sampled, prompts_by_id, response_by_pair,
                                        client=client2, tree=tree2, throttle=AdaptiveThrottle(tree2),
                                        rows_dir=rows_dir)
    assert n_scored_resume == 9
    assert load_completed_judge2_pairs(rows_dir) == set(sampled)

    df2 = second_judge.load_judge2_rows(rows_dir)
    assert len(df2) == 18

    rows = aggregate_agreement(df1, df2)
    assert len(rows) == 6
    assert {r["dim"] for r in rows} == {
        "factuality", "reasoning", "instruction_following",
        "format_compliance", "verbosity", "overall",
    }
    for r in rows:
        assert set(r.keys()) == set(second_judge.AGREEMENT_FIELDS)
        assert r["n"] == 18  # every sampled pair was scored by both judges

    out_path = tmp_path / "judge_agreement.csv"
    write_agreement_csv(rows, str(out_path))
    written = pd.read_csv(out_path)
    assert len(written) == 6
    assert list(written.columns) == second_judge.AGREEMENT_FIELDS
