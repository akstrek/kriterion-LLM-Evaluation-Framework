"""Guards against config/llm.py <-> Methods.tsx JUDGE_MODEL/JUDGE_SYSTEM_PROMPT drift.

Methods.tsx hand-mirrors these two constants (see the
`// Mirror of config/llm.py — keep in sync.` comment above them in the TSX)
because the Python source isn't importable from the frontend. Silent drift
here means the public methodology page renders a rubric that isn't the one
actually driving the judge — this test is what makes rubric edits (e.g. the
grounded-judging and multi-judge-ensemble revisions) safe to ship.

Extraction assumes the TS shape as of this writing:
  const JUDGE_MODEL = "...";                 (plain double-quoted string)
  const JUDGE_SYSTEM_PROMPT = `...`;         (template literal; may contain
                                               an escaped backtick as \\`)
If Methods.tsx is restyled (e.g. string concatenation instead of a template
literal, or the constants renamed), the regexes below will stop matching and
the assertions name exactly which one to fix.
"""
import difflib
import re

import pytest

from config.llm import JUDGE_MODEL, JUDGE_SYSTEM_PROMPT

METHODS_TSX_PATH = "src/components/pages/Methods.tsx"

_MODEL_RE = re.compile(r'const JUDGE_MODEL = "((?:[^"\\]|\\.)*)";')
_PROMPT_RE = re.compile(r'const JUDGE_SYSTEM_PROMPT = `([\s\S]*?)`;')


def _read_methods_tsx() -> str:
    with open(METHODS_TSX_PATH, encoding="utf-8") as f:
        return f.read()


def _extract_ts_mirror(ts_text: str) -> tuple[str, str]:
    model_match = _MODEL_RE.search(ts_text)
    assert model_match is not None, (
        f"Could not find `const JUDGE_MODEL = \"...\";` in {METHODS_TSX_PATH}. "
        "If the TS was restyled, update _MODEL_RE in test_mirror_sync.py."
    )
    ts_model = model_match.group(1).replace('\\"', '"').replace("\\\\", "\\")

    prompt_match = _PROMPT_RE.search(ts_text)
    assert prompt_match is not None, (
        f"Could not find the `const JUDGE_SYSTEM_PROMPT = `...`;` template literal "
        f"in {METHODS_TSX_PATH}. If the TS was restyled, update _PROMPT_RE in "
        "test_mirror_sync.py."
    )
    ts_prompt_raw = prompt_match.group(1)
    assert "${" not in ts_prompt_raw, (
        "JUDGE_SYSTEM_PROMPT mirror contains '${' template interpolation — "
        "raw-text comparison against the Python string is no longer valid. "
        "Update _extract_ts_mirror() to resolve the interpolation before comparing."
    )
    ts_prompt = ts_prompt_raw.replace("\\`", "`")
    return ts_model, ts_prompt


def _normalize(s: str) -> str:
    """Collapse CRLF -> LF and strip leading/trailing whitespace per line only.
    Blank lines and internal spacing are real content — the page renders this
    string in a <pre>, so drift in either is visible to a reader."""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.strip() for line in s.split("\n"))


def _assert_mirrors_equal(label: str, ts_value: str, py_value: str) -> None:
    ts_norm = _normalize(ts_value)
    py_norm = _normalize(py_value)
    if ts_norm == py_norm:
        return
    diff = "\n".join(difflib.unified_diff(
        py_norm.split("\n"), ts_norm.split("\n"),
        fromfile=f"config.llm.{label} (python)",
        tofile=f"Methods.tsx {label} (mirror)",
        lineterm="",
    ))
    raise AssertionError(f"{label} mirror drift between config/llm.py and Methods.tsx:\n{diff}")


def test_judge_model_mirror_matches():
    ts_model, _ = _extract_ts_mirror(_read_methods_tsx())
    _assert_mirrors_equal("JUDGE_MODEL", ts_model, JUDGE_MODEL)


def test_judge_system_prompt_mirror_matches():
    _, ts_prompt = _extract_ts_mirror(_read_methods_tsx())
    _assert_mirrors_equal("JUDGE_SYSTEM_PROMPT", ts_prompt, JUDGE_SYSTEM_PROMPT)


def test_drift_is_detected_with_a_diff():
    """Changing one character in the TS mirror must fail, and the failure
    message must carry a unified diff (not just 'not equal')."""
    tampered = JUDGE_SYSTEM_PROMPT.replace("factuality", "factualityX", 1)
    with pytest.raises(AssertionError, match=r"(?s)drift.*---.*\+\+\+"):
        _assert_mirrors_equal("JUDGE_SYSTEM_PROMPT", tampered, JUDGE_SYSTEM_PROMPT)


def test_interpolation_guard_rejects_template_expressions():
    ts_text_with_interp = (
        'const JUDGE_MODEL = "some/model:free";\n'
        'const JUDGE_SYSTEM_PROMPT = `hello ${name}`;'
    )
    with pytest.raises(AssertionError, match=r"\$\{"):
        _extract_ts_mirror(ts_text_with_interp)
