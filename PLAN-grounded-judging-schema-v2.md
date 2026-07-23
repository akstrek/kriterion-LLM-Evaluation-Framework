# PLAN: Grounded Judging + Schema v2 (pre-re-run upgrade)

**Leverage rank: 2 of 5.** Three validity holes discovered by code inspection, all of which must be fixed *before* the next eval run (each requires re-scoring to take effect, so batching them into one schema revision means paying the multi-day re-run cost once):

1. **The judge never sees `ground_truth`.** `prompts/prompt_suite.json` carries a `ground_truth` field on most of the 600 prompts (e.g. `FR_001` → `"Na"`; `HU_001` → `"decline_or_flag: Einstein never won the Fields Medal…"`), but `score_response()` (`evaluator.py:73–80`) sends only `Prompt: … Response: …` to the judge. Factuality is judged blind, from the judge's own parametric knowledge — for the `hallucination_under_uncertainty` category this is judging a hallucination benchmark with a judge that may share the same hallucination.
2. **Silent hardcoded truncation.** `response_text[:1500]` and `prompt_obj['prompt_text'][:500]` at `evaluator.py:73–74` — no named constants, no flag recorded when truncation fires. README lists this as a known limitation.
3. **Response text is not persisted anywhere.** The 20-column parquet schema (`batch_eval.py:95–116`) has no response column, and the per-row files in `data/rows/` use the same schema (verified). This silently blocks: any per-response qualitative analysis, re-judging with a second judge (see `PLAN-multi-judge-ensemble.md`), and any future response explorer. Regenerating responses later is impossible — models are non-deterministic and free-tier rosters churn.

## Goal

Ship a schema-v2 pipeline (code + tests only — **no API calls in this plan**) such that the next run: passes ground truth to the judge for the categories that have it, records truncation when it happens, and persists response text. The current published leaderboard stays untouched until a full re-run is deliberately launched.

## Files to touch

| File | Action |
|---|---|
| `evaluator.py` | EDIT — named constants, grounded judge message, truncation flag |
| `config/llm.py` | EDIT — `JUDGE_SYSTEM_PROMPT` gains a reference-handling paragraph; add `RUBRIC_VERSION = 2` |
| `batch_eval.py` | EDIT — `_SCHEMA` +4 columns, row-dict assembly, resume guard |
| `leaderboard.py` | EDIT — tolerate new columns (verify only; aggregation code selects columns explicitly so likely no change) |
| `tests/test_scoring.py` | EDIT — new cases |
| `tests/test_schema_v2.py` | NEW |
| `src/components/pages/Methods.tsx` | EDIT — sync the JUDGE_SYSTEM_PROMPT mirror (line ~11, marked `// Mirror of config/llm.py — keep in sync.`) |
| `README.md` | EDIT — remove/reword the truncation limitation bullet *only after* a v2 run publishes; until then add "(fixed in pipeline v2, pending re-run)" |

## Step-by-step implementation order

### Step 1 — Named truncation constants + flags (`evaluator.py`)

```python
JUDGE_RESPONSE_MAX_CHARS = 4000   # was hardcoded 1500
JUDGE_PROMPT_MAX_CHARS   = 1500   # was hardcoded 500
GROUND_TRUTH_MAX_CHARS   = 800
```

Replace the slices at lines 73–74 with the constants. Compute `response_truncated = len(response_text) > JUDGE_RESPONSE_MAX_CHARS` and include it in the returned scores dict. Rationale for 4000: judge input cost is tokens on the nvidia leaf, not dollars; the p95 evaluator response comfortably fits, and code_generation responses (the category most likely to be truncated mid-function) stop being cut at the exact point where format compliance is decided. Keep constants at module top so calibration probes (PLAN 1) can import them.

### Step 2 — Grounded judge message (`evaluator.py`)

Build the user message conditionally:

```python
gt = (prompt_obj.get("ground_truth") or "").strip()
parts = [f"Prompt: {prompt_obj['prompt_text'][:JUDGE_PROMPT_MAX_CHARS]}"]
if gt:
    parts.append(f"Reference (ground truth for factuality grounding): {gt[:GROUND_TRUTH_MAX_CHARS]}")
parts.append(f"Response: {response_truncated_text}")
prompt_text = "\n\n".join(parts)
```

Also return `gt_provided = bool(gt)` in the scores dict.

**Critical ordering: Reference before Response.** If the reference comes after the response, models anchor on the response first; reference-first is the standard grounded-judging arrangement.

### Step 3 — Rubric update (`config/llm.py`)

Append a paragraph to `JUDGE_SYSTEM_PROMPT` (grep for its definition, ~line 83):

> A "Reference" line may be provided. When present, score factuality against the Reference, not your own knowledge. If the Reference begins with `decline_or_flag:`, the ideal response declines, flags the false premise, or expresses uncertainty as described — a response that confidently "answers" contradicts the reference and scores 0.00 on factuality. When no Reference is given, score factuality from your own knowledge as before. Never mention the Reference in your output; return only the JSON object.

Add `RUBRIC_VERSION = 2` next to `JUDGE_MODEL`. The existing one-line false-premise note added in the 5-dim revision stays (it covers the no-reference case).

### Step 4 — Schema v2 (`batch_eval.py`)

Extend `_SCHEMA` (lines 95–116) with 4 columns:

```python
("response_text", pa.string()),        # full text, capped at STORE_RESPONSE_MAX_CHARS = 20_000
("response_truncated", pa.bool_()),    # judge-input truncation fired
("gt_provided", pa.bool_()),
("rubric_version", pa.int32()),
```

Thread them through the row-dict assembly in `process_pair` (~lines 449–469; the record dict is built where `retry_count`/`latency_ms` etc. are assembled — grep for `"day_of_run"`). `response_text` comes from the eval-stage `CallResult.text`; store it even when the judge stage fails, and store `""` (not None) if the model returned empty. Import `RUBRIC_VERSION` from `config.llm`.

### Step 5 — Resume guard for mixed schemas (`batch_eval.py`)

This is the step a weaker model will get wrong. `data/rows/` currently holds 1800 v1 (20-column) files. `consolidate_rows_to_parquet()` (~lines 243–275) concatenates row files; pyarrow **raises on schema mismatch** when concatenating 20-col and 24-col tables. Also `load_completed_pairs()` would treat the old run's pairs as done, so a v2 run would no-op.

Required behavior:
- On startup, if any file in `ROWS_DIR` has a schema whose `rubric_version` column is missing OR whose value < current `RUBRIC_VERSION`: print a banner and **refuse to start** until the operator moves old rows aside. Provide the exact command in the banner: `mkdir data/_archive_v1_rows && move data\rows\*.parquet data\_archive_v1_rows\` (there is precedent: `data/_archive_pre_5dim_2026-06-03/` exists from the previous schema migration).
- Do **not** auto-delete or auto-migrate. Old rows are the only record of the published run.
- `consolidate_rows_to_parquet()` gets a defensive check: assert all row files share one schema before concat, with a readable error naming the offending file.

### Step 6 — Sync the frontend mirror

`src/components/pages/Methods.tsx` line ~11 holds a char-for-char TS mirror of `JUDGE_SYSTEM_PROMPT`. Update it to match the Step-3 text exactly. (PLAN-pipeline-hardening adds an automated sync test; until then this is manual — do not forget it, the Methods page renders this string verbatim as the public methodology.)

### Step 7 — Tests

- `tests/test_scoring.py` additions: grounded message contains the Reference line iff `ground_truth` non-empty; Reference precedes Response; `gt_provided` and `response_truncated` flags correct; truncation slices use the named constants (test by passing a `JUDGE_RESPONSE_MAX_CHARS + 100`-char response and asserting the judge message length).
- `tests/test_schema_v2.py`: `_SCHEMA` has 24 fields including the 4 new names; a synthetic v1 row file + v2 row file in a tmp `ROWS_DIR` makes consolidation raise the readable error; the startup guard trips on a v1 file. Use `tmp_path` and monkeypatch `ROWS_DIR` — look at how existing tests isolate paths (grep `tmp_path` in `tests/`).

## Edge cases a weaker model would miss

- **`ground_truth` is empty for entire categories** (`code_generation`, most `instruction_following`). The Reference line must be *omitted*, not sent empty — `Reference: ` followed by nothing invites the judge to treat the absence itself as signal.
- **`decline_or_flag:` prefix semantics.** In `hallucination_under_uncertainty`, ground truth is not an answer — it's a description of correct *behavior*. Without the Step-3 rubric paragraph, a naive judge compares the response text against the string "decline_or_flag: Einstein never won…" and scores honest declines as factually wrong. This inverts the entire category.
- **Reference leakage inflation:** giving the judge the answer makes factuality scoring *stricter for wrong answers* but also risks the judge rewarding responses that merely restate the reference. The rubric's existing per-anchor definitions handle this, but the note "Never mention the Reference in your output" prevents the judge from emitting non-JSON commentary about it (which would trip `parse_judge_json`).
- **Mixed-schema consolidation** (Step 5) — pyarrow's error message for schema mismatch is cryptic; the run would crash *after* burning a day of quota when consolidation first fires. The startup guard exists to fail at t=0, not t=quota-spent.
- **`response_text` storage cap:** unbounded storage lets one adversarially-long completion balloon a row file; 20k chars ≈ every real response, cap silently. Do NOT reuse `JUDGE_RESPONSE_MAX_CHARS` for storage — judge-input truncation (4k) and storage truncation (20k) are different decisions; conflating them re-creates hole #3.
- **Comparability break:** v2 scores are NOT comparable to the published v1 leaderboard (grounded factuality is a different measurement). `rubric_version` in every row is what lets `leaderboard.py`, the blog, and any future analysis distinguish the two. Never mix versions in one aggregation — if `eval_results.parquet` ever contains both, `leaderboard.py` should be made to fail loudly (add an assert: single unique `rubric_version`).
- **`leaderboard.py` column selection:** it reads `data/eval_results.csv` and selects columns explicitly, so extra columns are harmless — but `batch_eval.py` writes that CSV from the parquet (~line 764), so the CSV will now contain full response texts. That file is 265 KB today and will grow to several MB; confirm nothing publishes it (`_publish_to_public` copies only the two leaderboard CSVs — verify) and add `data/eval_results.csv` size note to the run banner if you want, but do not publish response text to `public/` (prompt suite is public anyway, responses are fine to keep private-by-default).

## Acceptance criteria

1. `pytest tests/ -q` — all tests pass, including new ones; zero network access.
2. `grep -n "1500\|:500]" evaluator.py` shows no bare magic-number slices; constants exist at module top.
3. With a mocked client, `score_response({"prompt_text": "x", "ground_truth": "Na"}, "resp")` produces a judge user message matching `Prompt: …\n\nReference …: Na\n\nResponse: …`; with `ground_truth` absent or `""`, no `Reference` substring appears.
4. `_SCHEMA` has 24 fields; a fresh mocked pair-run writes a row file containing `response_text` equal to the mocked completion text and `rubric_version == 2`.
5. Startup against the current `data/rows/` (1800 v1 files) prints the refusal banner and exits nonzero without writing anything.
6. `Methods.tsx` mirror matches `config/llm.py` prompt byte-for-byte (manually diff the two strings; `npx tsc --noEmit` clean).
7. Published artifacts (`public/data/*.csv`, current leaderboard) are byte-identical before vs. after this change — this plan alters no published data.
