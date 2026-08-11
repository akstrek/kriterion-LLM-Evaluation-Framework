"""Prompt-suite fail-fast validation. A malformed suite must be caught before
any quota is spent — previously this surfaced as a mid-run KeyError, or
silently skewed stratified aggregation."""
import json

import pytest

import batch_eval
from batch_eval import PROMPT_SUITE_PATH, load_prompts, validate_prompt_suite
from generate_prompts import CATEGORIES, TARGET_PER_TIER


def _valid_suite() -> list[dict]:
    prompts = []
    i = 0
    for cat in CATEGORIES:
        for tier, count in TARGET_PER_TIER.items():
            for _ in range(count):
                i += 1
                prompts.append({
                    "id": f"{cat[:2].upper()}_{i:04d}",
                    "prompt_text": f"prompt text {i}",
                    "category": cat,
                    "difficulty": tier,
                    "ground_truth": "",
                })
    return prompts


def test_valid_synthetic_suite_passes():
    validate_prompt_suite(_valid_suite())  # no raise


def test_real_prompt_suite_passes():
    with open(PROMPT_SUITE_PATH, encoding="utf-8") as f:
        prompts = json.load(f)
    validate_prompt_suite(prompts)  # no raise


def test_missing_difficulty_names_the_id():
    prompts = _valid_suite()
    victim_id = prompts[0]["id"]
    del prompts[0]["difficulty"]
    with pytest.raises(ValueError, match=victim_id):
        validate_prompt_suite(prompts)


def test_duplicate_id_rejected():
    prompts = _valid_suite()
    prompts[1]["id"] = prompts[0]["id"]
    with pytest.raises(ValueError, match="Duplicate"):
        validate_prompt_suite(prompts)


def test_invalid_difficulty_value_rejected():
    prompts = _valid_suite()
    prompts[0]["difficulty"] = "impossible"
    with pytest.raises(ValueError, match="impossible"):
        validate_prompt_suite(prompts)


def test_unknown_category_rejected():
    prompts = _valid_suite()
    prompts[0]["category"] = "not_a_real_category"
    with pytest.raises(ValueError, match="not_a_real_category"):
        validate_prompt_suite(prompts)


def test_missing_ground_truth_key_rejected():
    prompts = _valid_suite()
    del prompts[0]["ground_truth"]
    with pytest.raises(ValueError, match="ground_truth"):
        validate_prompt_suite(prompts)


def test_empty_ground_truth_string_is_valid():
    prompts = _valid_suite()
    prompts[0]["ground_truth"] = ""
    validate_prompt_suite(prompts)  # no raise — key present, value may be empty


def test_wrong_total_count_rejected():
    prompts = _valid_suite()[:-1]
    with pytest.raises(ValueError, match="600"):
        validate_prompt_suite(prompts)


def test_wrong_tier_distribution_rejected():
    prompts = _valid_suite()
    # Flip one 'easy' to 'medium' within one category: total count (600) and
    # that category's own total (100) are both untouched, but the 15/25/35/25
    # split within the category is now wrong — must still be caught.
    cat = prompts[0]["category"]
    for p in prompts:
        if p["category"] == cat and p["difficulty"] == "easy":
            p["difficulty"] = "medium"
            break
    with pytest.raises(ValueError, match=cat):
        validate_prompt_suite(prompts)


def test_unknown_extra_key_does_not_fail():
    """Extra fields (schema v2 may add more) must not fail validation —
    only missing/invalid required fields do."""
    prompts = _valid_suite()
    prompts[0]["expected_output_type"] = "factual_answer"
    validate_prompt_suite(prompts)  # no raise


def test_load_prompts_exits_nonzero_naming_the_id(tmp_path, monkeypatch):
    prompts = _valid_suite()
    del prompts[5]["difficulty"]
    victim_id = prompts[5]["id"]
    suite_path = tmp_path / "prompt_suite.json"
    with open(suite_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f)

    monkeypatch.setattr(batch_eval, "PROMPT_SUITE_PATH", str(suite_path))
    with pytest.raises(SystemExit) as exc_info:
        load_prompts()
    assert victim_id in str(exc_info.value)
