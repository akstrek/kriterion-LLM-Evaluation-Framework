"""Schema-v2 tests: 24-column _SCHEMA, mixed v1/v2 row-file guards.
No network access — all row files here are synthetic pyarrow tables."""
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import batch_eval
from config.llm import RUBRIC_VERSION

NEW_V2_FIELDS = {"response_text", "response_truncated", "gt_provided", "rubric_version"}

# Mirrors the pre-schema-v2 _SCHEMA (20 columns, no response_text/rubric_version/etc.)
# so tests can synthesize a row file matching the real historical data/rows/*.parquet.
_V1_SCHEMA = pa.schema([
    pa.field("prompt_id",              pa.string()),
    pa.field("model",                  pa.string()),
    pa.field("factuality",             pa.float64()),
    pa.field("reasoning",              pa.float64()),
    pa.field("instruction_following",  pa.float64()),
    pa.field("format_compliance",      pa.float64()),
    pa.field("verbosity",              pa.float64()),
    pa.field("judge_empty",            pa.bool_()),
    pa.field("fallback_triggered",     pa.bool_()),
    pa.field("retry_count",            pa.int32()),
    pa.field("latency_ms",             pa.int64()),
    pa.field("tokens_used",            pa.int64()),
    pa.field("cost_usd",               pa.float64()),
    pa.field("provider",               pa.string()),
    pa.field("day_of_run",             pa.int32()),
    pa.field("difficulty",             pa.string()),
    pa.field("judge_model",            pa.string()),
    pa.field("parse_error",            pa.string()),
    pa.field("judge_latency_ms",       pa.int64()),
    pa.field("judge_tokens_used",      pa.int64()),
])


def _v1_row(prompt_id="P1", model="model_a"):
    record = {
        "prompt_id": prompt_id, "model": model,
        "factuality": 0.5, "reasoning": 0.5, "instruction_following": 0.5,
        "format_compliance": 0.5, "verbosity": 0.5,
        "judge_empty": False, "fallback_triggered": False, "retry_count": 0,
        "latency_ms": 100, "tokens_used": 50, "cost_usd": 0.0,
        "provider": "openrouter", "day_of_run": 1, "difficulty": "easy",
        "judge_model": "judge-x", "parse_error": "", "judge_latency_ms": 10,
        "judge_tokens_used": 5,
    }
    return pa.Table.from_pydict({k: [v] for k, v in record.items()}, schema=_V1_SCHEMA)


def _v2_row(prompt_id="P2", model="model_b"):
    record = {
        "prompt_id": prompt_id, "model": model,
        "factuality": 0.5, "reasoning": 0.5, "instruction_following": 0.5,
        "format_compliance": 0.5, "verbosity": 0.5,
        "judge_empty": False, "fallback_triggered": False, "retry_count": 0,
        "latency_ms": 100, "tokens_used": 50, "cost_usd": 0.0,
        "provider": "openrouter", "day_of_run": 1, "difficulty": "easy",
        "judge_model": "judge-x", "parse_error": "", "judge_latency_ms": 10,
        "judge_tokens_used": 5,
        "response_text": "hello", "response_truncated": False,
        "gt_provided": True, "rubric_version": RUBRIC_VERSION,
    }
    return pa.Table.from_pydict({k: [v] for k, v in record.items()}, schema=batch_eval._SCHEMA)


# ── _SCHEMA shape ─────────────────────────────────────────────────────────────


def test_schema_has_24_fields_including_new_columns():
    assert len(batch_eval._SCHEMA) == 24
    assert NEW_V2_FIELDS.issubset(set(batch_eval._SCHEMA.names))


# ── consolidate_rows_to_parquet: mixed schema raises readable error ──────────


def test_consolidate_raises_on_mixed_v1_v2_rows(tmp_path, monkeypatch):
    rows_dir = tmp_path / "rows"
    rows_dir.mkdir()
    pq.write_table(_v1_row(), rows_dir / "P1__model_a.parquet")
    pq.write_table(_v2_row(), rows_dir / "P2__model_b.parquet")

    monkeypatch.setattr(batch_eval, "ROWS_DIR", str(rows_dir))
    monkeypatch.setattr(batch_eval, "PARQUET_PATH", str(tmp_path / "eval_results.parquet"))

    with pytest.raises(ValueError, match="Row schema mismatch"):
        batch_eval.consolidate_rows_to_parquet()


def test_consolidate_succeeds_on_uniform_v2_rows(tmp_path, monkeypatch):
    rows_dir = tmp_path / "rows"
    rows_dir.mkdir()
    pq.write_table(_v2_row(prompt_id="P2", model="model_b"), rows_dir / "P2__model_b.parquet")
    pq.write_table(_v2_row(prompt_id="P3", model="model_c"), rows_dir / "P3__model_c.parquet")

    monkeypatch.setattr(batch_eval, "ROWS_DIR", str(rows_dir))
    monkeypatch.setattr(batch_eval, "PARQUET_PATH", str(tmp_path / "eval_results.parquet"))
    # EVALUATOR_MODELS filter must include our synthetic models or the rows
    # get filtered out by the active-roster mask.
    monkeypatch.setattr(batch_eval, "EVALUATOR_MODELS", ["model_b", "model_c"])

    n = batch_eval.consolidate_rows_to_parquet()
    assert n == 2


# ── Startup guard: trips on any v1 row file present ──────────────────────────


def test_startup_guard_trips_on_v1_file(tmp_path, monkeypatch, capsys):
    rows_dir = tmp_path / "rows"
    rows_dir.mkdir()
    pq.write_table(_v1_row(), rows_dir / "P1__model_a.parquet")

    monkeypatch.setattr(batch_eval, "ROWS_DIR", str(rows_dir))

    with pytest.raises(SystemExit) as exc_info:
        batch_eval.check_row_schema_guard()
    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "STALE ROW SCHEMA" in captured.out


def test_startup_guard_passes_on_all_v2_files(tmp_path, monkeypatch):
    rows_dir = tmp_path / "rows"
    rows_dir.mkdir()
    pq.write_table(_v2_row(), rows_dir / "P2__model_b.parquet")

    monkeypatch.setattr(batch_eval, "ROWS_DIR", str(rows_dir))
    # Should not raise.
    batch_eval.check_row_schema_guard()


def test_startup_guard_noop_when_rows_dir_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_eval, "ROWS_DIR", str(tmp_path / "does_not_exist"))
    # Should not raise.
    batch_eval.check_row_schema_guard()
