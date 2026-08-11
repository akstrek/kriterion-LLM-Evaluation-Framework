"""retune_weights.py: advisory HTB weight recompute. Read-only, offline — it
never writes config/llm.py. Exercises the demand/pressure/proposal math in
isolation; running it for real against data/ is a separate manual step."""
import json

import pandas as pd
import pytest

import retune_weights as rw
from config.llm import (
    EVALUATOR_MODELS,
    FALLBACK_MAP,
    _EVAL_PROVIDERS,
    _PROVIDER_RATES,
    _split_eval_budget,
)


def test_split_eval_budget_replica_matches_config_llm():
    """The locally-replicated formula (config.llm._split_eval_budget reads a
    module global, so it can't be called with a proposed dict) must agree
    with the real function when given identical rates."""
    assert rw.split_eval_budget_with_rates(_PROVIDER_RATES) == _split_eval_budget()


def test_split_eval_budget_replica_handles_zero_total_weight():
    zero_rates = {p: 0.0 for p in _EVAL_PROVIDERS}
    assert rw.split_eval_budget_with_rates(zero_rates) == {p: 0 for p in _EVAL_PROVIDERS}


def test_fallback_demand_routes_through_fallback_map_not_parquet_model():
    """Parquet 'model' is always the *requested* id, never the served one. A
    50% fallback rate on model X must show up as redirected demand on
    FALLBACK_MAP[X]'s provider, not attributed to X's own provider."""
    model_x = EVALUATOR_MODELS[0]
    x_provider = model_x.split("/")[0]
    fb_id = FALLBACK_MAP[model_x]
    fb_provider = fb_id.split("/")[0]

    n = 100
    df = pd.DataFrame([
        {"prompt_id": f"P{i}", "model": model_x, "fallback_triggered": (i % 2 == 0)}
        for i in range(n)
    ])

    demand = rw.compute_demand(df)
    assert demand[x_provider] == pytest.approx(n)         # primary: 1 per pair
    assert demand[fb_provider] == pytest.approx(n * 0.5)  # redirected: fallback_rate * n


def test_compute_demand_handles_missing_dataframe():
    assert rw.compute_demand(None) == {p: 0.0 for p in _EVAL_PROVIDERS}


def test_compute_demand_handles_empty_dataframe():
    assert rw.compute_demand(pd.DataFrame()) == {p: 0.0 for p in _EVAL_PROVIDERS}


def test_judge_stage_429_does_not_affect_eval_pressure():
    entries = [
        {"prompt_id": "P1", "model": "nvidia/nemotron-3-super-120b-a12b:free",
         "stage": "judge", "error": "Error code: 429 - rate limited",
         "timestamp": "2026-08-01T00:00:00+00:00"},
    ]
    daily_peak, raw_daily = rw.compute_pressure(entries)
    assert daily_peak == {}
    assert raw_daily == {}


def test_eval_stage_429_is_counted_by_provider_and_daily_peak():
    model = EVALUATOR_MODELS[0]
    provider = model.split("/")[0]
    entries = [
        {"prompt_id": "P1", "model": model, "stage": "eval",
         "error": "Error code: 429 - temporarily rate-limited upstream",
         "timestamp": "2026-08-01T10:00:00+00:00"},
        {"prompt_id": "P2", "model": model, "stage": "eval",
         "error": "Error code: 429 - temporarily rate-limited upstream",
         "timestamp": "2026-08-01T11:00:00+00:00"},
        {"prompt_id": "P3", "model": model, "stage": "eval",
         "error": "Error code: 429 - temporarily rate-limited upstream",
         "timestamp": "2026-08-02T10:00:00+00:00"},
    ]
    daily_peak, raw_daily = rw.compute_pressure(entries)
    assert daily_peak[provider] == 2  # peak day (08-01, 2 events), not the 3 total
    assert raw_daily[provider] == {"2026-08-01": 2, "2026-08-02": 1}


def test_non_429_and_malformed_error_strings_dont_crash():
    model = EVALUATOR_MODELS[0]
    entries = [
        {"prompt_id": "P1", "model": model, "stage": "eval",
         "error": "Error code: 500 - server error", "timestamp": "2026-08-01T00:00:00+00:00"},
        {"prompt_id": "P2", "model": model, "stage": "eval",
         "error": "totally unparseable garbage with no code at all",
         "timestamp": "2026-08-01T00:00:00+00:00"},
        {"prompt_id": "P3", "model": model, "stage": "eval",
         "error": None, "timestamp": "2026-08-01T00:00:00+00:00"},
        {"prompt_id": "P4", "stage": "eval", "error": "Error code: 429",
         "timestamp": "not-a-real-timestamp"},  # missing 'model' too
        {"prompt_id": "P5", "stage": "eval"},    # missing 'error' and 'timestamp'
    ]
    daily_peak, raw_daily = rw.compute_pressure(entries)  # must not raise
    assert isinstance(daily_peak, dict)
    assert isinstance(raw_daily, dict)


def test_propose_rates_floors_zero_demand_providers():
    demand = {p: 0.0 for p in _EVAL_PROVIDERS}
    demand[_EVAL_PROVIDERS[0]] = 100.0
    proposed = rw.propose_rates(demand)
    for p in _EVAL_PROVIDERS[1:]:
        assert proposed[p] == pytest.approx(rw.MIN_WEIGHT_FLOOR)
    assert proposed[_EVAL_PROVIDERS[0]] > rw.MIN_WEIGHT_FLOOR


def test_propose_rates_all_zero_demand_floors_everything():
    demand = {p: 0.0 for p in _EVAL_PROVIDERS}
    assert rw.propose_rates(demand) == {p: rw.MIN_WEIGHT_FLOOR for p in _EVAL_PROVIDERS}


def test_propose_rates_preserves_total_weight_mass_when_even():
    demand = {p: 100.0 for p in _EVAL_PROVIDERS}
    proposed = rw.propose_rates(demand)
    current_mass = sum(_PROVIDER_RATES[p] for p in _EVAL_PROVIDERS)
    assert sum(proposed.values()) == pytest.approx(current_mass, abs=1e-3)


def test_load_failed_calls_since_filter(tmp_path, monkeypatch):
    path = tmp_path / "failed_calls.json"
    entries = [
        {"prompt_id": "old", "timestamp": "2026-01-01T00:00:00+00:00"},
        {"prompt_id": "new", "timestamp": "2026-08-01T00:00:00+00:00"},
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f)
    monkeypatch.setattr(rw, "FAILED_PATH", str(path))
    monkeypatch.setattr(rw, "DATA_DIR", str(tmp_path))

    since_filtered = rw.load_failed_calls(since="2026-06-01", include_archives=False)
    assert [e["prompt_id"] for e in since_filtered] == ["new"]

    unfiltered = rw.load_failed_calls(since=None, include_archives=False)
    assert len(unfiltered) == 2


def test_load_failed_calls_include_archives(tmp_path, monkeypatch):
    live = tmp_path / "failed_calls.json"
    archive = tmp_path / "failed_calls_2026-07-01.json"
    with open(live, "w", encoding="utf-8") as f:
        json.dump([{"prompt_id": "live", "timestamp": "2026-08-01T00:00:00+00:00"}], f)
    with open(archive, "w", encoding="utf-8") as f:
        json.dump([{"prompt_id": "archived", "timestamp": "2026-07-01T00:00:00+00:00"}], f)
    monkeypatch.setattr(rw, "FAILED_PATH", str(live))
    monkeypatch.setattr(rw, "DATA_DIR", str(tmp_path))

    without = rw.load_failed_calls(since=None, include_archives=False)
    assert [e["prompt_id"] for e in without] == ["live"]

    with_archives = rw.load_failed_calls(since=None, include_archives=True)
    assert sorted(e["prompt_id"] for e in with_archives) == ["archived", "live"]


def test_load_failed_calls_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(rw, "FAILED_PATH", str(tmp_path / "does_not_exist.json"))
    monkeypatch.setattr(rw, "DATA_DIR", str(tmp_path))
    assert rw.load_failed_calls(since=None, include_archives=False) == []


def test_load_failed_calls_malformed_json_does_not_crash(tmp_path, monkeypatch):
    path = tmp_path / "failed_calls.json"
    path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(rw, "FAILED_PATH", str(path))
    monkeypatch.setattr(rw, "DATA_DIR", str(tmp_path))
    assert rw.load_failed_calls(since=None, include_archives=False) == []


def test_load_eval_results_missing_file_returns_none(tmp_path):
    assert rw.load_eval_results(str(tmp_path / "does_not_exist.parquet")) is None


def test_default_since_reads_state_started_at(tmp_path, monkeypatch):
    state_path = tmp_path / "eval_state.json"
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"started_at": "2026-07-15T09:00:00+00:00"}, f)
    monkeypatch.setattr(rw, "STATE_PATH", str(state_path))
    assert rw._default_since() == "2026-07-15"


def test_default_since_missing_state_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(rw, "STATE_PATH", str(tmp_path / "does_not_exist.json"))
    assert rw._default_since() is None


def test_main_runs_offline_with_no_data_and_exits_zero(tmp_path, monkeypatch, capsys):
    """Smoke test: no data/ present, no network — must still complete and
    print a report, never raising or touching config/llm.py."""
    monkeypatch.setattr(rw, "PARQUET_PATH", str(tmp_path / "eval_results.parquet"))
    monkeypatch.setattr(rw, "FAILED_PATH", str(tmp_path / "failed_calls.json"))
    monkeypatch.setattr(rw, "STATE_PATH", str(tmp_path / "eval_state.json"))
    monkeypatch.setattr(rw, "DATA_DIR", str(tmp_path))

    rw.main([])  # must not raise

    out = capsys.readouterr().out
    assert "proposed" in out.lower()
    assert "current" in out.lower()


def test_main_json_flag_emits_valid_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rw, "PARQUET_PATH", str(tmp_path / "eval_results.parquet"))
    monkeypatch.setattr(rw, "FAILED_PATH", str(tmp_path / "failed_calls.json"))
    monkeypatch.setattr(rw, "STATE_PATH", str(tmp_path / "eval_state.json"))
    monkeypatch.setattr(rw, "DATA_DIR", str(tmp_path))

    rw.main(["--json"])

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert set(payload["current_rates"]) == set(_EVAL_PROVIDERS)
    assert set(payload["proposed_rates"]) == set(_EVAL_PROVIDERS)
