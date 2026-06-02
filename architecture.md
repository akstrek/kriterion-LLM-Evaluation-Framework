# Kriterion — Architecture

Source-of-truth doc. Reflects code as it exists, not the build summary's narrative.

## 1. FILE TREE

```
kriterion/
├── batch_eval.py              # Daily runner; wires EvalOrchestrator + per-row parquet checkpoints
├── evaluator.py               # run_model() + score_response() — both route through call_model()
├── leaderboard.py             # eval_results.csv → leaderboard.csv (overall_applicable + overall_strict + CI)
├── generate_prompts.py        # Emits prompts/prompt_suite.json (200 prompts)
├── requirements.txt           # Python deps (openai, pandas, numpy, pyarrow, dotenv, tqdm)
├── README.md
├── Kriterion_Build_Summary.md # Historical narrative — superseded by this doc
├── config/
│   ├── __init__.py
│   ├── llm.py                 # call_model(), HTB tree, adaptive throttle, FALLBACK_MAP, prompts
│   └── scheduler.py           # BoundedPairQueue, DRRScheduler, EvalOrchestrator, quota-sleep helper
├── tests/                     # pytest suite — zero real API calls (mocks throughout)
│   ├── conftest.py            # Sets OPENROUTER_API_KEY stub before kriterion imports
│   ├── test_htb.py            # HTB token refill, borrowing, ceiling, daily decrement, reset
│   ├── test_drr.py            # DRR fairness under quota pressure, htb_check gating
│   ├── test_scoring.py        # Empty-judge NaN, overall_strict imputation, bootstrap CI bounds
│   └── test_fallback.py       # Mock OpenAI client — fallback triggers, retry_count, provider debit
├── prompts/
│   └── prompt_suite.json      # 200 prompts (5 cats × 40)
├── index.html                 # Vite entry
├── package.json               # React 19 + Vite 6 + TS 5.8 + Tailwind 4 + Shadcn + Recharts
├── tsconfig.json
├── vite.config.ts
├── components.json            # shadcn-ui config
├── src/
│   ├── main.tsx               # React root
│   ├── App.tsx                # Routes: /, /rankings, /dimensions, /frontier, /methods, /blog
│   ├── index.css
│   ├── lib/
│   │   ├── loadCsv.ts         # Fetch /data/leaderboard.csv; FALLBACK_DATA on miss
│   │   └── utils.ts           # cn() helper
│   ├── types/index.ts         # ModelPerformance interface
│   ├── components/
│   │   ├── pages/             # Overview, Rankings, Dimensions, Frontier, Methods, Blog
│   │   ├── layout/            # PageFrame, Navbar, BottomLeft, BottomRight,
│   │   │                      # CtaButton, ExpandableViz, GrainOverlay, ScrollableZone
│   │   └── charts/            # CostQualityScatter, DimensionDeepDive,
│   │                          # LeaderboardTable, RadarComparison
├── components/ui/             # shadcn primitives: badge, button, chart,
│                              # dropdown-menu, separator, tooltip
├── lib/utils.ts               # cn() (duplicate path used by shadcn imports)
├── public/
│   └── background.webp        # NOTE: public/data/ does not exist — see GAPS
└── docs/screenshots/overview.png
```

Not in repo (would be produced by a run): `data/rows/*.parquet`, `data/eval_results.parquet`, `data/eval_results.csv`, `data/leaderboard.csv`, `data/eval_state.json`, `data/eval_metadata.json`, `data/failed_calls.json`. (No `schedule_next_run.bat` — quota-exhaustion sleep is in-process; see §3.)

## 2. MODEL CONFIG

| Role | Model ID (config/llm.py) | Fallback (FALLBACK_MAP) |
|---|---|---|
| Evaluator | `moonshotai/kimi-k2.6:free`              | `google/gemma-4-26b-a4b-it:free` |
| Evaluator | `openai/gpt-oss-20b:free`                | `google/gemma-4-31b-it:free`     |
| Evaluator | `openai/gpt-oss-120b:free`               | `google/gemma-4-31b-it:free`     |
| Judge     | `nvidia/nemotron-3-super-120b-a12b:free` | `nvidia/nemotron-3-nano-30b-a3b:free` |

The current evaluator roster — `moonshotai/kimi-k2.6:free`, `google/gemma-4-31b-it:free`, `openai/gpt-oss-120b:free` — shares HTB leaves with their fallback hops: `kimi → gemma-4-26b-a4b-it` debits the `google` leaf, `gemma-4-31b-it → gpt-oss-20b` debits the `openai` leaf, and `gpt-oss-120b → gemma-4-31b-it` also debits the `google` leaf. This is why the `google` leaf carries the largest daily budget (it absorbs two lanes' fallback traffic plus its own primary).

Fallback hops are taken **once** after `MAX_RETRY=2` primary attempts exhaust. The fallback also passes through HTB on its own provider — see §3.

API routing (config/llm.py:86-89):
```python
_client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)
```

`:free`-only enforcement at import — applied to evaluator + judge models **and every entry in `FALLBACK_MAP`** (both keys and values). Any non-`:free` id raises `ValueError` at module load.

Per-call: `temperature=0.0`, `extra_body={"provider": {"allow_fallbacks": False}}` — unavailable `:free` variants 4xx rather than silently routing to paid providers. The model-level fallback in `FALLBACK_MAP` is a Kriterion concern, not OpenRouter's routing fallback.

Evaluator system prompt (config/llm.py:79-84) — identical across all three evaluators:
```
You are a helpful, precise AI assistant. Answer the user's prompt directly.
Be concise. Be accurate. Follow all formatting instructions exactly.
If the prompt asks for a specific format (JSON, list, code), use that format only.
Do not add disclaimers, caveats, or meta-commentary about your response.
```

Judge system prompt (config/llm.py:70-77) — verbatim:
```
Score this prompt-response pair. Use full 0.00-1.00 range — most responses score 0.40-0.85, not 1.00.
factuality: claim accuracy. 1.00=every claim verifiable. 0.85=minor imprecision. 0.60=one wrong claim. 0.30=multiple errors. 0.00=fabricated. null if no factual claims.
reasoning: inferential validity AND depth. 1.00=correct + insightful. 0.85=correct but shallow. 0.60=mostly correct, one weak step. 0.30=flawed logic. 0.00=incoherent. null if no reasoning required.
instruction_following: constraint satisfaction. Count explicit constraints (length, format, scope, exclusions). Score = constraints_met / constraints_total. Partial credit per constraint. Score implied intent if none explicit.
format_compliance: structural exactness. 1.00=perfect structure. 0.85=correct structure, minor deviation. 0.60=right format, wrong details. 0.30=wrong format. 0.00=no structure attempted.
Penalize: hedging, padding, unnecessary preamble, repetition. Reward: precision, completeness within minimal tokens.
Return JSON only: {"factuality":0.00,"reasoning":0.00,"instruction_following":0.00,"format_compliance":0.00}
null example: {"factuality":null,"reasoning":null,"instruction_following":0.85,"format_compliance":0.92}
```

## 3. EVAL PIPELINE

### 3.1 LLM surface (config/llm.py)

Single public entry point: `call_model(model_id, messages, role) -> CallResult` where `role ∈ {"evaluator","judge"}`. Returns a dataclass:

```
CallResult(text, latency_ms, tokens_used, model_used, fallback_triggered, retry_count, parse_error)
```

`model_used` reflects the model actually called — when the fallback hop fires, `model_used` is the fallback id and `fallback_triggered=True`. `htb_status() -> dict` returns a live snapshot of the HTB tree for telemetry.

Run constants:

| Constant | Value | Source |
|---|---|---|
| Root rate | 0.3 req/sec (18 RPM) | config/llm.py `_ROOT_RATE` |
| Root ceil (burst) | 0.3 req/sec | config/llm.py `_ROOT_CEIL` |
| Root daily budget | 950 RPD | config/llm.py `_ROOT_RPD` |
| Eval daily sub-budget | 650 RPD, split by guarantee weight | `_EVAL_RPD` + `_split_eval_budget()` |
| Judge daily sub-budget | 300 RPD on `nvidia` | `_JUDGE_RPD` |
| `MAX_RETRY` | 2 (initial + 1 retry) | config/llm.py |
| `_RETRY_DELAYS` | `[30]` seconds | config/llm.py |
| Adaptive throttle trigger | trailing-60s 429 rate > 30% | `AdaptiveThrottle.THROTTLE_TRIGGER` |
| Throttled root rate | 0.15 req/sec for 300s cooldown | `_THROTTLED_RATE` |

### 3.2 Hierarchical Token Bucket (HTB)

Tree (single tree-wide `threading.Lock`):

```
root (0.3/s, ceil 0.3, RPD 950, burst 5)
 ├── nvidia       (0.10/s,  RPD 300)   ← judge only
 ├── openai       (0.05/s,  RPD 163)
 ├── moonshotai   (0.05/s,  RPD 163)
 └── google       (0.10/s,  RPD 325)   ← double weight: own primary + inbound gemma fallback hops
```

Eval providers are `openai`, `moonshotai`, `google`; their per-leaf RPD is computed from `_PROVIDER_RATES` weights via `_split_eval_budget()`.

- `HTBNode.refill()` is continuous: `tokens = min(ceil, tokens + elapsed * rate_per_sec)`.
- `HTBTree.acquire(provider)` walks leaf→root: every node on the path must have ≥1 token AND `daily_remaining > 0`. On success it decrements both at every node; otherwise it blocks for the worst-case wait, capped at 5s per spin.
- **Daily budget decrements on every gross attempt** (including 429 retries) — mirrors OpenRouter's accounting.
- `ceil_per_sec` equals the root rate for every leaf, so an idle sibling's token budget can be fully borrowed (the root's bucket is the only hard ceiling).
- `reset_daily()` walks the tree and restores every `daily_remaining` to its initial `daily_budget` — invoked on the 00:01 UTC wake.

### 3.3 Adaptive throttle

`AdaptiveThrottle` keeps a 60s deque of `(timestamp, was_429)` events. With ≥5 samples and 429-rate > 30%, it halves the root's `rate_per_sec` to 0.15/s and arms a 300s cooldown; on cooldown expiry the rate is restored. State transitions log to stdout. Records are written from `_attempt_one` after every API response (success or 429).

### 3.4 Retry + fallback orchestration (call_model)

1. Up to `MAX_RETRY=2` attempts on the primary, each gated by `HTBTree.acquire(primary_provider)` and separated by a 30s `_interruptible_sleep`.
2. On exhaustion **or** on `DailyQuotaExhausted` from the primary's path, one attempt on `FALLBACK_MAP[model_id]` if defined — also gated by `HTBTree.acquire(fallback_provider)`. Fallback debits the fallback's HTB leaf, not the primary's.
3. If everything fails, the last exception is raised. `DailyQuotaExhausted` propagates all the way to `EvalOrchestrator`.

### 3.5 DRR scheduler (config/scheduler.py)

- `BoundedPairQueue(maxsize=50)` is a `queue.Queue` of `(prompt_obj, model)` tuples — backpressure for slow workers.
- `DRRScheduler(models, quantum=1)`: per-model deficit counter. `next_pair(htb_check)` advances the cursor round-robin; lanes with empty pending reset their deficit to 0; lanes blocked by `htb_check` are skipped without consuming quantum. Returns `None` when no lane is eligible — the orchestrator's signal to sleep briefly.
- `EvalOrchestrator(models, process_pair_fn)` wires 1 scheduler thread + `len(models)`=3 worker threads to the queue. Workers `process_pair_fn(prompt_obj, model)` (eval call → judge call → write parquet row). All shared state mutations behind a single `state_lock`.

### 3.6 Quota-exhausted sleep path

When any worker raises `DailyQuotaExhausted`, it requeues the offending pair to the front of its DRR lane and sets `quota_event`. The scheduler thread:

1. `queue.join()` drains in-flight workers.
2. `sleep_until_reset(stop_event, poll_secs=300)` polls every 5 min until the next 00:01 UTC — the polling interval is what makes the loop survive a Windows suspend/resume.
3. On wake: `HTBTree.reset_daily()`, clear `quota_event`, resume.

This entirely replaces the old `schtasks` / `schedule_next_run.bat` mechanism — the runner stays in-process across the reset boundary.

### 3.7 Checkpointing + state

Atomic per-row parquet writes via `tmp → fsync → os.replace`: `data/rows/{prompt_id}__{model-safe-name}.parquet`, O(1) per pair. Consolidated to `data/eval_results.parquet` + `data/eval_results.csv` only on clean completion. The consolidation step filters rows by current `EVALUATOR_MODELS` via `pyarrow.compute.is_in` so stale rows from prior roster changes (e.g. a model removed between runs) never leak into the leaderboard. `data/eval_state.json` writes use the same atomic pattern with 5×0.2s retry on Windows `PermissionError`.

`eval_state.json` schema:

```
{
  "total_calls":      int,
  "total_failures":   int,
  "resume_events":    int,
  "day_of_run":       int,
  "started_at":       ISO-UTC,
  "htb_snapshot":     { ...output of htb_status() at last write... },
  "credits_at_start": { usage, limit, checked_at }
}
```

Fields removed from the old schema: `last_exhausted`, `next_run_utc`, `pending_evals`. The eval/judge HTB sub-budgets cannot bleed into one another, so the mid-judge `pending_evals` checkpoint is no longer needed — a daily exhaustion on the judge leaf still wastes at most one eval call, the same as before, but the bookkeeping is no longer a separate code path.

### 3.8 Resume + failure logging

- `load_completed_pairs()` = `(prompt_id, model)` set from `eval_results.parquet` ∪ every row file in `data/rows/`, filtered against current `EVALUATOR_MODELS` (so a model removed from the roster between runs no longer marks its prior `(prompt_id, stale_model)` pairs as done). `todo_pairs` = `(prompts × EVALUATOR_MODELS) − completed`. `resume_events` incremented when `len(completed_pairs) > 0` on startup.
- `failed_calls.json` is appended (atomically) after `MAX_RETRY` retries + 1 fallback all fail on either `eval` or `judge` stage. Entry shape unchanged: `{prompt_id, model, stage, error, [eval_latency_ms], timestamp}`.
- Credit telemetry (`fetch_key_info()` → `GET /api/v1/key`) is preserved; pre-flight and post-run print usage/limit/remaining, and warn on `spent > $0.01`.

### 3.9 Key architecture decisions

1. **HTB over flat RPM bucket.** A single 18-RPM global bucket couldn't express provider weights (nvidia is 40% of all calls, google is 0%). HTB lets every provider have a guaranteed share, full borrowing up to the root ceiling when siblings are idle, and a separate daily decrement that mirrors OpenRouter's free-tier accounting.
2. **Eval and judge HTB sub-budgets are sibling-independent.** Splitting 950 RPD into 650 (eval, weighted across moonshotai/openai/google) and 300 (judge on nvidia) makes it structurally impossible to exhaust the judge mid-pair while eval succeeds — that eliminated the `pending_evals` checkpoint and `_QuotaSignal` plumbing.
3. **DRR over `ThreadPoolExecutor.submit` for fairness.** With workers ≪ pairs, FIFO submission lets a single slow provider starve the others. DRR with quantum=1 + an `htb_check` gate guarantees per-model progress and skips lanes whose provider is currently tokenless without burning quantum.
4. **In-process quota sleep replaces `schtasks`.** A 5-min poll loop until 00:01 UTC handles Windows suspend/resume without a separate scheduled task; the runner no longer needs `sys.exit` + re-launch.
5. **Single fallback hop, no chains.** `MAX_RETRY=2` then one fallback model. Chains amplify cost on the bad path and obscure attribution; one hop is enough to absorb most transient outages.
6. **All non-applicable judge dimensions are NaN.** No 0.0 defaults anywhere — see §4.

## 4. SCORING

Dimensions (judge JSON schema, parsed in `evaluator.score_response`):

| Dim | Type | NaN when |
|---|---|---|
| `factuality` | float | judge returns `null` (no factual claims), OR judge response was empty/unparseable |
| `reasoning` | float | judge returns `null` (no reasoning required), OR judge response was empty/unparseable |
| `instruction_following` | float | judge response was empty/unparseable |
| `format_compliance` | float | judge response was empty/unparseable |

Anchor points (judge system prompt): 1.00 / 0.85 / 0.60 / 0.30 / 0.00 per dimension. Range mandate: `most responses score 0.40-0.85, not 1.00`.

Truncation before judge: response cap 1500 chars, prompt cap 500 chars (unchanged).

JSON parsing:
- Strips ` ```json ` / ` ``` ` fences.
- `json.loads` → coerce each present key, `None` → `float("nan")`, missing key → `parse_error="Missing keys: [...]"`.
- `JSONDecodeError`, non-object body, or empty `result.text` → `judge_empty=True`, all four dims set to NaN, `parse_error` populated with the reason.

`overall_applicable` = `np.nanmean([factuality, reasoning, instruction_following, format_compliance])` per row — excludes NaN dims. Replaces the old `overall_score` column.

`overall_strict` is computed in `leaderboard.py` (not at row time): per row, each NaN dim is imputed with that model's own mean for that dim across all rows, then averaged. Penalises models the judge couldn't score on a dim — no free pass for skipping.

**Empty-judge fix.** Previously, an empty judge response left `instruction_following` and `format_compliance` at 0.0 defaults while NaN-ing the other two — silently underscoring models. The new behaviour: ALL FOUR dims become NaN and `judge_empty=True` is recorded on the row, so those rows can be filtered, counted (`n_judge_empty` per model on the leaderboard), or imputed by the strict aggregator.

Parquet schema (current — old rows are NOT migrated):
```
prompt_id str | model str
factuality f64 | reasoning f64 | instruction_following f64 | format_compliance f64
overall_applicable f64
judge_empty bool | fallback_triggered bool | retry_count i32
latency_ms i64 | tokens_used i64 | cost_usd f64 (always 0.0 on :free)
provider str ("openrouter") | day_of_run i32
judge_model str | parse_error str | judge_latency_ms i64 | judge_tokens_used i64
```

Fields removed vs prior schema: `overall_score`, `factuality_null`, `reasoning_null`, `is_fallback`. Replaced by `overall_applicable` + `judge_empty` + `fallback_triggered` (now meaningful) + `retry_count`.

Leaderboard aggregation (`leaderboard.compute_leaderboard`):
- Group by `model`; per-dimension means (`avg_<dim>`) via `pd.Series.mean(skipna=True)`.
- `overall_applicable`: column mean of per-row `overall_applicable`.
- `overall_strict`: per-row impute-then-average using each model's own dim means.
- `ci_low` / `ci_high`: 95% bootstrap CI on `overall_applicable` per row — 1000 resamples, seed 42, pure numpy. Sanity-checked in `tests/test_scoring.py`.
- `latency_p50_ms`, `latency_p95_ms`, `avg_tokens_used`, `total_cost_usd`, `avg_cost_per_prompt_usd`, `score_per_dollar` (numeric or `"N/A (free tier)"`).
- `cat_<category>` per category, joined via `prompts/prompt_suite.json` — now averages `overall_applicable`, not `overall_score`.
- Diagnostics: `n_judge_empty`, `n_fallback`, `n_prompts`.
- Sorted desc by `overall_applicable`, ranked 1..N.

## 5. FRONTEND

Routes (src/App.tsx:6-26):

| Route | Lazy import | File |
|---|---|---|
| `/` | `Overview` | src/components/pages/Overview.tsx |
| `/rankings` | `Rankings` | src/components/pages/Rankings.tsx |
| `/dimensions` | `Dimensions` | src/components/pages/Dimensions.tsx |
| `/frontier` | `Frontier` | src/components/pages/Frontier.tsx |
| `/methods` | `Methods` | src/components/pages/Methods.tsx |
| `/blog` | `Blog` | src/components/pages/Blog.tsx |

Wrapped in `<PageFrame>` + `<AnimatePresence>` (motion). Suspense fallback `null`.

Layout components: `PageFrame`, `Navbar`, `BottomLeft`, `BottomRight`, `CtaButton`, `ExpandableViz`, `GrainOverlay`, `ScrollableZone`.

Chart components: `CostQualityScatter`, `DimensionDeepDive`, `LeaderboardTable`, `RadarComparison`.

Data loading (src/lib/loadCsv.ts):
- `loadLeaderboard()` fetches `/data/leaderboard.csv`, papaparse with `header:true, dynamicTyping:true`. Numeric coercion + `|| 0` for every field (lines 58-67).
- `loadEvalResults()` is an alias of `loadLeaderboard` (line 81-83).
- `loadDimensions()` returns the hard-coded list `["Factuality", "Reasoning", "Instruction Following", "Format Compliance"]`.
- `FALLBACK_DATA` (lines 4-35) is used on fetch failure / wrong content-type / parse error. Currently contains **placeholder** rows for Claude Sonnet 4, GPT-4o, Gemini Flash 2.0 — NOT the real evaluators. See GAPS.

Stack (package.json): React 19, react-dom 19, react-router-dom 7, Vite 6, TypeScript 5.8, Tailwind 4 + `@tailwindcss/vite`, Recharts 3, motion 12, papaparse 5, shadcn primitives (radix-ui slot), lucide + hugeicons.

Dev: `npm run dev` → `vite --port=3000 --host=0.0.0.0`. Build: `vite build`. Lint: `tsc --noEmit`.

## 6. DEPLOYMENT

| Target | What | How |
|---|---|---|
| Vercel | React static site | `vite build` → `dist/`. Runtime fetch of `/data/leaderboard.csv` (must live at `public/data/leaderboard.csv` pre-build). |
| Local Windows | Python eval harness | `python batch_eval.py [-y]`. Resumes via `schedule_next_run.bat` registered with `schtasks` on quota exhaustion. |

Env vars:

| Var | Required by | Behaviour if missing |
|---|---|---|
| `OPENROUTER_API_KEY` | config/llm.py:20-25 | Module raises `EnvironmentError` at import — fail-fast. |

Loaded via `python-dotenv` from a `.env` file at repo root.

Python deps (requirements.txt):
```
openai>=1.30.0
pandas>=2.0.0
numpy>=1.26.0
pyarrow>=15.0.0
python-dotenv>=1.0.0
tqdm>=4.66.0
```

No FastAPI, no Modal, no Railway, no server-side runtime. CSV is the wire format between Python and React.

## 7. GAPS

Items still divergent from `Kriterion_Build_Summary.md` or otherwise pending:

- **`public/data/` directory does not exist** — only `public/background.webp` is present. Production fetch of `/data/leaderboard.csv` will 404 and trigger `FALLBACK_DATA` until a CSV is placed there (copy `data/leaderboard.csv` after `leaderboard.py` runs).
- **Frontend fallback content**: `src/lib/loadCsv.ts` `FALLBACK_DATA` still contains placeholder labels (Claude Sonnet 4, GPT-4o, Gemini Flash 2.0) — not the current evaluator model IDs (`moonshotai/kimi-k2.6:free`, `google/gemma-4-31b-it:free`, `openai/gpt-oss-120b:free`). Misleading if the real CSV is missing.
- **`loadCsv.ts` schema mismatch**: the frontend papaparse loader still expects the legacy `overall_score` shape. The new CSV exports `overall_applicable` / `overall_strict` / `ci_low` / `ci_high` — the loader and `ModelPerformance` type need updating before a real run feeds the dashboard.
- **Calibration probes**: noted in the rewrite spec as future work; not implemented this revision.
- **HTB provider weights are still hand-set, not learned.** `_PROVIDER_RATES` was rebalanced this revision (see "Resolved" below for the math); the weekly recompute against `failed_calls.json` + parquet success-rate logs is still not automated. Re-tune by hand if a run shows one eval lane binding materially earlier than the others.
- **Smoke verification only**: tests use mocked OpenAI clients (zero real API calls). End-to-end verification against live OpenRouter is deferred — it burns RPD and requires explicit approval per session.
- **`Kriterion_Build_Summary.md` itself**: still referenced as authoritative by some upstream tasks — superseded by this doc.

Resolved since the prior revision (no longer gaps):

- Empty-judge handling now NaN-s all four dims and sets `judge_empty=True` — matches the original intent.
- `eval_state.json` no longer carries `pending_evals` / `last_exhausted` / `next_run_utc`; the in-process quota-sleep loop replaces the `schtasks` round-trip.
- Per-provider 4.0s gap + 18-RPM sliding window superseded by the HTB tree.
- `tests/` directory exists — 24 mocked tests cover HTB, DRR, scoring, and fallback.
- **First full run completed** — `data/eval_results.csv` exists (600 pairs across the current 3-evaluator roster). `leaderboard.py` is unblocked.
- **Stale-row leak fixed** — `load_completed_pairs()` and `consolidate_rows_to_parquet()` now filter by current `EVALUATOR_MODELS` via `pyarrow.compute.is_in`. Surfaced when 16 prior-roster `deepseek/*` rows in `data/rows/` were silently consolidated into the leaderboard as a ghost lane with all-1.0 dim scores (from fallback-hop responses recorded under the requested model id).
- **`Blog.tsx` model-cards revision** — 4 compound cards (Judge + 3 Evaluators) with role badges, provider glyphs (simple-icons SVG for OpenAI/Google/NVIDIA, monogram for MoonshotAI), architecture-type pill (MoE/Dense/Hybrid/LatentMoE), and click-to-expand inline fallbacks. Section 04 rewritten around HTB + DRR with an inline ASCII tree; Section 05 updated to the new `overall_applicable`/`overall_strict`/`ci_low`/`ci_high`/`n_judge_empty`/`n_fallback` schema; Section 07 evaluator roster corrected; new "Traffic Shaping the Free Tier" pitch section inserted between header and Section 01.
- **Eval-budget mis-allocation under current model layout** (was: openai 488 / moonshotai 81 / google 81 RPD). Root cause: `_PROVIDER_RATES` carried the 0.15-vs-0.025 prior from a layout where `openai/*` hosted **two** primary evaluators (`gpt-oss-20b` + `gpt-oss-120b`) on a shared provider lane, and small open-weight providers were prior-flagged as flaky. Current `EVALUATOR_MODELS` is one model per provider (`kimi-k2.6` on moonshotai, `gemma-4-31b-it` on google, `gpt-oss-120b` on openai), so the 6× openai skew left moonshotai/google binding hard (~81 RPD vs ~158 needed/day) while openai sat on +330 RPD of unused budget. Rate side wasn't load-bearing — every leaf's `ceil_per_sec` equals the root rate, so leaves fully borrow; weights only affected `_split_eval_budget()`. Fix applied: `_PROVIDER_RATES = {nvidia: 0.10, openai: 0.05, moonshotai: 0.05, google: 0.10}` — equal across the two non-fallback-receiving eval lanes, double weight for google since two other lanes' fallback hops (kimi → gemma-4-26b, gpt-oss-120b → gemma-4-31b) land on its leaf. New eval split: openai 163 / moonshotai 163 / google 325 RPD. Judge (nvidia 300 RPD) unchanged.
