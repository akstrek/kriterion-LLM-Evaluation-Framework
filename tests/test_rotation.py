"""failed_calls.json rotation: a fresh run starts a clean failure log; a
resumed run must never disturb the current run's history mid-flight."""
import datetime
import json
from datetime import timezone

import batch_eval
from batch_eval import rotate_failed_calls_if_fresh


def _write(path, entries) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f)


_ENTRY = {"prompt_id": "P1", "model": "m", "stage": "eval", "error": "x", "timestamp": "t"}


def test_fresh_run_rotates_nonempty_file(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_eval, "DATA_DIR", str(tmp_path))
    failed_path = tmp_path / "failed_calls.json"
    monkeypatch.setattr(batch_eval, "FAILED_PATH", str(failed_path))
    _write(failed_path, [_ENTRY])

    rotate_failed_calls_if_fresh(is_resume=False)

    assert not failed_path.exists()
    rotated = list(tmp_path.glob("failed_calls_*.json"))
    assert len(rotated) == 1
    with open(rotated[0], encoding="utf-8") as f:
        assert json.load(f) == [_ENTRY]


def test_resume_leaves_file_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_eval, "DATA_DIR", str(tmp_path))
    failed_path = tmp_path / "failed_calls.json"
    monkeypatch.setattr(batch_eval, "FAILED_PATH", str(failed_path))
    _write(failed_path, [_ENTRY])

    rotate_failed_calls_if_fresh(is_resume=True)

    assert failed_path.exists()
    with open(failed_path, encoding="utf-8") as f:
        assert json.load(f) == [_ENTRY]
    assert list(tmp_path.glob("failed_calls_*.json")) == []


def test_fresh_run_with_no_existing_file_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_eval, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(batch_eval, "FAILED_PATH", str(tmp_path / "failed_calls.json"))

    rotate_failed_calls_if_fresh(is_resume=False)  # no raise

    assert list(tmp_path.glob("failed_calls_*.json")) == []


def test_fresh_run_with_empty_list_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_eval, "DATA_DIR", str(tmp_path))
    failed_path = tmp_path / "failed_calls.json"
    monkeypatch.setattr(batch_eval, "FAILED_PATH", str(failed_path))
    _write(failed_path, [])

    rotate_failed_calls_if_fresh(is_resume=False)

    assert failed_path.exists()  # nothing to rotate — left in place
    assert list(tmp_path.glob("failed_calls_*.json")) == []


def test_collision_appends_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_eval, "DATA_DIR", str(tmp_path))
    failed_path = tmp_path / "failed_calls.json"
    monkeypatch.setattr(batch_eval, "FAILED_PATH", str(failed_path))

    date_str = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d")
    existing_dest = tmp_path / f"failed_calls_{date_str}.json"
    existing_dest.write_text("[]", encoding="utf-8")  # simulates same-day prior rotation

    _write(failed_path, [_ENTRY])

    rotate_failed_calls_if_fresh(is_resume=False)

    assert not failed_path.exists()
    suffixed = tmp_path / f"failed_calls_{date_str}_1.json"
    assert suffixed.exists()
    with open(suffixed, encoding="utf-8") as f:
        assert json.load(f) == [_ENTRY]
    # The pre-existing same-day file must survive untouched.
    with open(existing_dest, encoding="utf-8") as f:
        assert json.load(f) == []


def test_unreadable_file_is_rotated_not_lost(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_eval, "DATA_DIR", str(tmp_path))
    failed_path = tmp_path / "failed_calls.json"
    monkeypatch.setattr(batch_eval, "FAILED_PATH", str(failed_path))
    failed_path.write_text("{not valid json", encoding="utf-8")

    rotate_failed_calls_if_fresh(is_resume=False)

    assert not failed_path.exists()
    assert list(tmp_path.glob("failed_calls_*.json"))
