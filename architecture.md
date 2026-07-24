# Kriterion — Architecture

Source-of-truth doc. Reflects code as it exists, not the build summary's narrative.

## 1. FILE TREE

```
kriterion/
├── batch_eval.py              # Daily runner; wires EvalOrchestrator + per-row parquet checkpoints
├── evaluator.py               # run_model() + score_response() — both route through call_model(); build_judge_user_message() shared with second_judge.py
├── leaderboard.py             # eval_results.csv → leaderboard.csv (overall_applicable + overall_strict + CI)
├── calibration_probes.py      # Judge reliability runner: 32 anchor probes × 3 repeats → data/judge_calibration.csv
├── second_judge.py            # Offline re-scoring of a 300-pair deterministic sample by a 2nd judge → data/judge_agreement.csv
├── generate_prompts.py        # Emits prompts/prompt_suite.json (600 prompts, 6 cats × 100, difficulty-tagged)
├── requirements.txt           # Python deps (openai, pandas, numpy, pyarrow, dotenv, tqdm)
├── README.md
├── config/
│   ├── __init__.py
│   ├── llm.py                 # call_model(), HTB tree, adaptive throttle, FALLBACK_MAP, prompts
│   └── scheduler.py           # BoundedPairQueue, DRRScheduler, EvalOrchestrator, quota-sleep helper
├── tests/                     # pytest suite — zero real API calls (mocks throughout)
│   ├── conftest.py            # Sets OPENROUTER_API_KEY stub before kriterion imports
│   ├── test_htb.py            # HTB token refill, borrowing, ceiling, daily decrement, reset
│   ├── test_drr.py            # DRR fairness under quota pressure, htb_check gating
│   ├── test_scoring.py        # Empty-judge NaN (5-dim), HEADLINE_DIMS excludes format_compliance, overall_strict imputation, bootstrap CI
│   ├── test_fallback.py       # Mock OpenAI client — fallback triggers, retry_count, provider debit
│   ├── test_retry.py          # Retry-After / X-RateLimit-Reset honoring, full-jitter backoff bounds, is_retryable classes, 4xx fail-fast, 5xx retry
│   ├── test_calibration.py    # parse_judge_json round-trip, probe-suite validation, band-hit/parse-failure/test-retest-std aggregation (mocked)
│   └── test_second_judge.py   # deterministic sampling, agreement math (Pearson/MAE/null-disagreement), message parity, judge2 HTB debit, resume (mocked)
├── prompts/
│   ├── prompt_suite.json      # 600 prompts (6 cats × 100; each prompt tagged easy/medium/hard/expert at 15/25/35/25)
│   └── calibration_probes.json # 32 anchor (prompt, response) pairs — 6 per dim (2 high/2 mid/2 low) × 5 dims + 2 null-checks
├── index.html                 # Vite entry
├── package.json               # React 19 + Vite 6 + TS 5.8 + Tailwind 4 + Shadcn + Recharts
├── tsconfig.json
├── vite.config.ts
├── vercel.json                # SPA rewrite: all paths → /index.html. `git.deploymentEnabled.main:false` gates auto-deploy off main until flipped back on (see §6).
├── components.json            # shadcn-ui config
├── src/
│   ├── main.tsx               # React root
│   ├── App.tsx                # Routes: /, /rankings, /dimensions, /methods, /blog
│   ├── index.css
│   ├── lib/
│   │   ├── loadCsv.ts         # Fetch /data/leaderboard.csv + /data/leaderboard_by_difficulty.csv + /data/judge_calibration.csv + /data/judge_agreement.csv; FALLBACK_DATA on miss (calibration/agreement return [] on miss, no fallback data)
│   │   ├── modelColors.ts     # Family-based color registry + modelDisplayName()
│   │   └── utils.ts           # cn() helper
│   ├── types/index.ts         # ModelPerformance + ModelDifficultyRow + JudgeCalibrationRow + JudgeAgreementRow interfaces
│   ├── components/
│   │   ├── pages/             # Overview, Rankings, Dimensions, Methods, Blog
│   │   ├── layout/            # PageFrame, Navbar, BottomLeft, BottomRight,
│   │   │                      # CtaButton, ExpandableViz, GrainOverlay, ScrollableZone,
│   │   │                      # ScrollToTop
│   │   └── charts/            # DimensionDeepDive, LeaderboardTable,
│   │                          # PerformanceLatencyScatter, RadarComparison, DifficultyBreakdown
├── components/ui/             # shadcn primitives: badge, button, chart,
│                              # dropdown-menu, separator, tooltip
├── lib/utils.ts               # cn() (duplicate path used by shadcn imports)
├── public/
│   ├── background.webp
│   └── data/                  # leaderboard.csv + leaderboard_by_difficulty.csv + judge_calibration.csv + judge_agreement.csv (if present), auto-published by leaderboard.py._publish_to_public()
└── docs/screenshots/overview.png
```

Not in repo (would be produced by a run): `data/rows/*.parquet`, `data/eval_results.parquet`, `data/eval_results.csv`, `data/leaderboard.csv`, `data/leaderboard_by_difficulty.csv`, `data/judge_calibration.csv`, `data/calibration_runs.csv`, `data/judge2_rows/*.parquet`, `data/judge_agreement.csv`, `data/eval_state.json`, `data/eval_metadata.json`, `data/failed_calls.json`. (No `schedule_next_run.bat` — quota-exhaustion sleep is in-process; see §3.)

## 2. MODEL CONFIG

| Role | Model ID (config/llm.py) | Fallback (FALLBACK_MAP) |
|---|---|---|
| Evaluator | `moonshotai/kimi-k2.6:free`              | `google/gemma-4-26b-a4b-it:free` |
| Evaluator | `openai/gpt-oss-20b:free`                | `google/gemma-4-31b-it:free`     |
| Evaluator | `openai/gpt-oss-120b:free`               | `google/gemma-4-31b-it:free`     |
| Judge     | `nvidia/nemotron-3-super-120b-a12b:free` | `nvidia/nemotron-3-nano-30b-a3b:free` |
| Judge 2 (offline agreement sample only, never headline-blended) | `poolside/laguna-m.1:free` | `poolside/laguna-s-2.1:free` |

The current evaluator roster — `moonshotai/kimi-k2.6:free`, `google/gemma-4-31b-it:free`, `openai/gpt-oss-120b:free` — shares HTB leaves with their fallback hops: `kimi → gemma-4-26b-a4b-it` debits the `google` leaf, `gemma-4-31b-it → gpt-oss-20b` debits the `openai` leaf, and `gpt-oss-120b → gemma-4-31b-it` also debits the `google` leaf. This is why the `google` leaf carries the largest daily budget (it absorbs two lanes' fallback traffic plus its own primary).

Fallback hops are taken **once** after the primary's retries exhaust (`MAX_RETRY=3` attempts) **or** immediately when the primary returns a non-retryable error (see §3.4). The fallback also passes through HTB on its own provider — see §3.

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

Judge system prompt (config/llm.py) — verbatim:
```
Score this prompt-response pair. Use full 0.00-1.00 range — most responses score 0.40-0.85, not 1.00.
factuality: claim accuracy. 1.00=every claim verifiable. 0.85=minor imprecision. 0.60=one wrong claim. 0.30=multiple errors. 0.00=fabricated. null if no factual claims.
reasoning: inferential validity AND depth. 1.00=correct + insightful. 0.85=correct but shallow. 0.60=mostly correct, one weak step. 0.30=flawed logic. 0.00=incoherent. null if no reasoning required.
instruction_following: constraint satisfaction. Count explicit constraints (length, format, scope, exclusions). Score = constraints_met / constraints_total. Partial credit per constraint. Score implied intent if none explicit.
format_compliance: structural exactness. 1.00=perfect structure. 0.85=correct structure, minor deviation. 0.60=right format, wrong details. 0.30=wrong format. 0.00=no structure attempted.
verbosity: conciseness relative to task. 1.00=optimal length, no padding. 0.85=slightly verbose. 0.60=noticeable padding or hedging. 0.30=significant bloat. 0.00=severe rambling. Penalize unnecessary preamble, repetition, hedging. Reward precision within minimal tokens.
When the prompt contains a false premise or unanswerable request, correctly identifying this and declining to fabricate is the high-scoring response; do not penalize absence of factual claims in that case.
Return JSON only: {"factuality":0.00,"reasoning":0.00,"instruction_following":0.00,"format_compliance":0.00,"verbosity":0.00}
null example: {"factuality":null,"reasoning":null,"instruction_following":0.85,"format_compliance":0.92,"verbosity":0.78}
```

Headline policy is enforced in `leaderboard.HEADLINE_DIMS = [factuality, reasoning, instruction_following, verbosity]` — `format_compliance` is still scored on every response and reported as `avg_format_compliance`, but excluded from `overall_applicable`. The 5th dimension `verbosity` replaces the prior trailing `Penalize:` line and is part of the headline mean.

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
| Root daily budget | 1300 RPD | config/llm.py `_ROOT_RPD` |
| Eval daily sub-budget | 650 RPD, split by guarantee weight | `_EVAL_RPD` + `_split_eval_budget()` |
| Judge daily sub-budget | 300 RPD on `nvidia` | `_JUDGE_RPD` |
| Judge 2 daily sub-budget | 350 RPD on `poolside` | `_JUDGE2_RPD` |
| `MAX_RETRY` | 3 (initial + 2 retries) | config/llm.py |
| Retry backoff | Retry-After header if present, else full-jitter exp `random.uniform(0, min(60, 2·2ⁿ))` | `_compute_backoff()` / `_retry_after_seconds()` |
| `_BACKOFF_BASE` / `_BACKOFF_CAP` | 2.0s / 60.0s (cap also clamps server header) | config/llm.py |
| Node burst | 2 permits (keeps post-idle peak < 20 RPM) | config/llm.py `_NODE_BURST` |
| Adaptive throttle trigger | trailing-60s 429 rate > 30% | `AdaptiveThrottle.THROTTLE_TRIGGER` |
| Throttled root rate | 0.15 req/sec for 300s cooldown | `_THROTTLED_RATE` |
| Sweep passes / gaps | 4 passes; 5/15/30 min between retry sweeps | `batch_eval.SWEEP_MAX_PASSES` / `SWEEP_SLEEPS_SECS` (see §3.8) |

### 3.2 Hierarchical Token Bucket (HTB)

Tree (single tree-wide `threading.Lock`):

```
root (0.3/s, ceil 0.3, RPD 1300, burst 2)
 ├── nvidia       (0.10/s,  RPD 300)   ← judge only
 ├── openai       (0.05/s,  RPD 163)
 ├── moonshotai   (0.05/s,  RPD 163)
 ├── google       (0.10/s,  RPD 325)   ← double weight: own primary + inbound gemma fallback hops
 └── poolside     (0.05/s,  RPD 350)   ← judge2 only (second_judge.py); primary + fallback share this one leaf
```

Eval providers are `openai`, `moonshotai`, `google`; their per-leaf RPD is computed from `_PROVIDER_RATES` weights via `_split_eval_budget()`. Root RPD is 1300 (950 eval+judge1 + 350 judge2) — raised from 950 this revision after confirming the OpenRouter account has crossed the credits threshold that lifts the free-tier daily cap from 50 to 1000/day.

- `HTBNode.refill()` is continuous: `tokens = min(ceil, tokens + elapsed * rate_per_sec)`.
- `HTBTree.acquire(provider)` walks leaf→root: every node on the path must have ≥1 token AND `daily_remaining > 0`. On success it decrements both at every node; otherwise it blocks for the worst-case wait, capped at 5s per spin.
- **Daily budget decrements on every gross attempt** (including 429 retries) — intentional, because OpenRouter counts failed 429 requests against the free-tier daily quota, so the local counter must mirror that to enter the quota-sleep at the right time. (This is why the retry mechanics in §3.4 minimize *wasted* 429s rather than relaxing this accounting.)
- **Node burst is 2 permits** so a post-idle catch-up can't push the root over OpenRouter's 20 RPM free-tier ceiling (peak/60s ≈ 2 + 0.3·58 ≈ 19.4 < 20).
- `ceil_per_sec` equals the root rate for every leaf, so an idle sibling's token budget can be fully borrowed (the root's bucket is the only hard ceiling).
- `reset_daily()` walks the tree and restores every `daily_remaining` to its initial `daily_budget` — invoked on the 00:01 UTC wake.

### 3.3 Adaptive throttle

`AdaptiveThrottle` keeps a 60s deque of `(timestamp, was_429)` events. With ≥5 samples and 429-rate > 30%, it halves the root's `rate_per_sec` to 0.15/s and arms a 300s cooldown; on cooldown expiry the rate is restored. State transitions log to stdout. Records are written from `_attempt_one` after every API response (success or 429).

### 3.4 Retry + fallback orchestration (call_model)

1. Up to `MAX_RETRY=3` attempts on the primary, each gated by `HTBTree.acquire(primary_provider)`. Between attempts, `_interruptible_sleep(_compute_backoff(last_exc, attempt))` waits: the server's `Retry-After` / `X-RateLimit-Reset` header when present (clamped to `_BACKOFF_CAP`, plus sub-second jitter so the workers don't re-sync), otherwise full-jitter exponential backoff. This replaces the old fixed `[30, 90]`s schedule.
2. **Retry-class discrimination (`is_retryable`).** Only 429 / 5xx / timeouts / connection errors are retried. Non-retryable errors — 4xx client errors and empty `choices` — break out of the retry loop immediately (no sleep, no extra gross attempt) and drop straight to the fallback hop, so they don't burn daily-quota units on attempts that can't succeed. The OpenRouter daily-cap 429 (`free-models-per-day`) is still converted to `DailyQuotaExhausted` *before* the classifier and is never retried.
3. On exhaustion **or** on `DailyQuotaExhausted` from the primary's path, one attempt on `FALLBACK_MAP[model_id]` if defined — also gated by `HTBTree.acquire(fallback_provider)`. Fallback debits the fallback's HTB leaf, not the primary's.
4. If everything fails, the last exception is raised. `DailyQuotaExhausted` propagates all the way to `EvalOrchestrator`.

### 3.5 DRR scheduler (config/scheduler.py)

- `BoundedPairQueue(maxsize=50)` is a `queue.Queue` of `(prompt_obj, model)` tuples — backpressure for slow workers.
- `DRRScheduler(models, quantum=1)`: per-model deficit counter. `next_pair(htb_check)` advances the cursor round-robin; lanes with empty pending reset their deficit to 0; lanes blocked by `htb_check` are skipped without consuming quantum. Returns `None` when no lane is eligible — the orchestrator's signal to sleep briefly.
- `EvalOrchestrator(models, process_pair_fn)` wires 1 scheduler thread + `len(models)`=3 worker threads to the queue. Workers `process_pair_fn(prompt_obj, model)` (eval call → judge call → write parquet row). All shared state mutations behind a single `state_lock`.

### 3.6 Quota-exhausted sleep path

When any worker raises `DailyQuotaExhausted`, it requeues the offending pair to the front of its DRR lane and sets `quota_event`. The scheduler thread:

1. `queue.join()` drains in-flight workers.
2. `target = next_utc_reset()` computes the reset moment **once**; `on_quota_enter(target)` fires (status box prints).
3. `sleep_until_reset(stop_event, reset_at=target, poll_secs=300, on_tick=on_quota_tick)` polls every 5 min until the target — the polling interval is what makes the loop survive a Windows suspend/resume. `on_tick` emits a compact `[wake-check]` heartbeat after each poll.
4. On wake: `HTBTree.reset_daily()`, clear `quota_event`, `on_quota_resume()` bumps `state["day_of_run"]` and prints the resume banner. Resume.

Callbacks (`on_quota_enter`, `on_quota_tick`, `on_quota_resume`) are optional `EvalOrchestrator.__init__` parameters; `batch_eval.py` supplies closures that read live `state` + `orch.stats.completed` and render the status blocks (`_print_quota_exhausted_box`, `_print_wake_tick`, `_print_resume_banner`, `_print_completion_box`). No timing or scheduling logic changes through callbacks — they are pure stdout.

This entirely replaces the old `schtasks` / `schedule_next_run.bat` mechanism — the runner stays in-process across the reset boundary.

### 3.7 Checkpointing + state

Atomic per-row parquet writes via `tmp → fsync → os.replace`: `data/rows/{prompt_id}__{model-safe-name}.parquet`, O(1) per pair. Consolidated to `data/eval_results.parquet` + `data/eval_results.csv` only on clean completion. **`consolidate_rows_to_parquet()` rebuilds the parquet from `ROWS_DIR` alone** — the row files are the single source of truth (each is the latest evaluation for its pair, since `os.replace` overwrites in place), so it does **not** re-read the prior `eval_results.parquet`. The consolidation step filters rows by current `EVALUATOR_MODELS` via `pyarrow.compute.is_in` so stale rows from prior roster changes (e.g. a model removed between runs) never leak into the leaderboard, and a defensive de-dup on `(prompt_id, model)` keeps consolidation idempotent. `data/eval_state.json` writes use the same atomic pattern with 5×0.2s retry on Windows `PermissionError`.

`eval_state.json` schema:

```
{
  "total_calls":      int,
  "total_failures":   int,
  "resume_events":    int,
  "day_of_run":       int,        # bumped by on_quota_resume() across a UTC reset
  "n_fallback":       int,        # cumulative fallback-hop count (incremented in process_pair)
  "n_judge_empty":    int,        # cumulative judge_empty=True row count
  "started_at":       ISO-UTC,
  "htb_snapshot":     { ...output of htb_status() at last write... },
  "credits_at_start": { usage, limit, checked_at }
}
```

`load_state()` `setdefault`s the new counters so resumed runs from pre-revision state files still load. Fields removed from the old schema (still): `last_exhausted`, `next_run_utc`, `pending_evals`.

### 3.8 Resume + failure logging

- `load_completed_pairs()` = `(prompt_id, model)` set from `eval_results.parquet` ∪ every row file in `data/rows/`, filtered against current `EVALUATOR_MODELS` (so a model removed from the roster between runs no longer marks its prior `(prompt_id, stale_model)` pairs as done). `todo_pairs` = `(prompts × EVALUATOR_MODELS) − completed`. `resume_events` incremented when `len(completed_pairs) > 0` on startup.
- `failed_calls.json` is appended (atomically) after `MAX_RETRY` retries + 1 fallback all fail on either `eval` or `judge` stage. Entry shape unchanged: `{prompt_id, model, stage, error, [eval_latency_ms], timestamp}`. A pair that lands here wrote **no** parquet row, so it re-enters `todo_pairs` on the next pass/run.
- **Patient multi-pass sweep (`batch_eval.main`).** A *transient* upstream 429 (`"…temporarily rate-limited upstream. Please retry shortly"`) is **not** the daily-cap signal (`free-models-per-day`) and is **not** `DailyQuotaExhausted`, so it never triggers the §3.6 quota-sleep+requeue. After `MAX_RETRY` + 1 fallback it is logged to `failed_calls.json` and dropped — the pair is un-evaluated but eligible for `todo_pairs`. A single immediate re-run hits the same instantaneous throttle, so such pairs can persist as a tail (observed: 67/1800, ~96% `kimi-k2.6` whose only fallback `gemma-4-26b` lands on an also-throttled `google` leaf). Fix: `main()` wraps the orchestrator pass in a bounded sweep loop (`run_one_pass()` helper). After each pass it recomputes the still-missing pairs from disk via `load_completed_pairs()`; if any remain it `_interruptible_sleep`s an increasing gap (`SWEEP_SLEEPS_SECS = [300, 900, 1800]` → 5/15/30 min) to let the upstream throttle clear, then re-runs the **existing** `EvalOrchestrator` over only the remainder, up to `SWEEP_MAX_PASSES = 4`. The inter-pass gap is the entire fix — it is the spacing a manual re-run lacks. **No change to HTB, DRR, the scheduler/worker, retry mechanics, scoring, or frontend** — the sweep adds nothing inside a pass and reuses `EvalOrchestrator`, `make_process_pair`, the `on_quota_{enter,tick,resume}` callbacks, and `enqueue_all`/`run()` verbatim. The §3.6 daily-cap quota-sleep still fires independently inside `run()` mid-pass when the real cap is hit. Run summary (`Completed/Failed/Quota sleeps`) accumulates across passes; residual un-evaluated pairs after the last pass are reported, not silently dropped. `Ctrl+C` during a gap exits cleanly with checkpoints saved.
- Credit telemetry (`fetch_key_info()` → `GET /api/v1/key`) is preserved; pre-flight and post-run print usage/limit/remaining, and warn on `spent > $0.01`.

### 3.9 Key architecture decisions

1. **HTB over flat RPM bucket.** A single 18-RPM global bucket couldn't express provider weights (nvidia is 40% of all calls, google is 0%). HTB lets every provider have a guaranteed share, full borrowing up to the root ceiling when siblings are idle, and a separate daily decrement that mirrors OpenRouter's free-tier accounting.
2. **Eval and judge HTB sub-budgets are sibling-independent.** Splitting 950 RPD into 650 (eval, weighted across moonshotai/openai/google) and 300 (judge on nvidia) makes it structurally impossible to exhaust the judge mid-pair while eval succeeds — that eliminated the `pending_evals` checkpoint and `_QuotaSignal` plumbing.
3. **DRR over `ThreadPoolExecutor.submit` for fairness.** With workers ≪ pairs, FIFO submission lets a single slow provider starve the others. DRR with quantum=1 + an `htb_check` gate guarantees per-model progress and skips lanes whose provider is currently tokenless without burning quantum.
4. **In-process quota sleep replaces `schtasks`.** A 5-min poll loop until 00:01 UTC handles Windows suspend/resume without a separate scheduled task; the runner no longer needs `sys.exit` + re-launch.
5. **Single fallback hop, no chains.** `MAX_RETRY=3` (with Retry-After-aware backoff) then one fallback model. Chains amplify cost on the bad path and obscure attribution; one hop is enough to absorb most transient outages.
6. **All non-applicable judge dimensions are NaN.** No 0.0 defaults anywhere — see §4.

## 4. SCORING

Dimensions (judge JSON schema, parsed in `evaluator.score_response`). The cross-ref pair is `evaluator.EXPECTED_SCORE_KEYS` ↔ `leaderboard.DIMENSIONS` — both are five-element sets, kept in sync by a one-line comment in each module:

| Dim | In headline? | Type | NaN when |
|---|---|---|---|
| `factuality` | ✓ | float | judge returns `null` (no factual claims), OR judge response was empty/unparseable |
| `reasoning` | ✓ | float | judge returns `null` (no reasoning required), OR judge response was empty/unparseable |
| `instruction_following` | ✓ | float | judge response was empty/unparseable |
| `format_compliance` | ✗ (reported only) | float | judge response was empty/unparseable |
| `verbosity` | ✓ | float | judge response was empty/unparseable |

`HEADLINE_DIMS` (single source of truth in `leaderboard.py`) = the four ✓ rows. `format_compliance` is still scored on every prompt and reported as `avg_format_compliance`, but excluded from `overall_applicable` — structural pickiness is a separate axis from capability.

Anchor points (judge system prompt): 1.00 / 0.85 / 0.60 / 0.30 / 0.00 per dimension. Range mandate: `most responses score 0.40-0.85, not 1.00`. The judge prompt also carries a one-line conditional: when the prompt contains a false premise or unanswerable request, correctly identifying that and declining to fabricate is the high-scoring response — `factuality=null` is *not* a penalty in that case. `RUBRIC_VERSION=2` (config/llm.py) adds a Reference-handling paragraph: when a prompt's `ground_truth` is non-empty, the judge is sent a `Reference (ground truth for factuality grounding): …` line (before the Response, per the standard grounded-judging arrangement) and told to score factuality against it — a `decline_or_flag:`-prefixed reference means the ideal response declines/flags/expresses uncertainty, so a confident "answer" scores `factuality=0.00`. No Reference line is sent when `ground_truth` is empty (most of `code_generation`/`instruction_following`).

Truncation before judge: response cap raised 1500 → 4000 chars (`evaluator.JUDGE_RESPONSE_MAX_CHARS`), prompt cap 500 → 1500 chars (`JUDGE_PROMPT_MAX_CHARS`), reference cap 800 chars (`GROUND_TRUTH_MAX_CHARS`). `response_truncated` (judge-input truncation fired) and `gt_provided` (ground_truth was non-empty) are now returned by `score_response` and persisted per row — distinct from `batch_eval.STORE_RESPONSE_MAX_CHARS=20_000`, the separate cap on what's persisted to parquet.

JSON parsing:
- Strips ` ```json ` / ` ``` ` fences.
- `json.loads` → coerce each present key, `None` → `float("nan")`, missing key → `parse_error="Missing keys: [...]"`.
- `JSONDecodeError`, non-object body, or empty `result.text` → `judge_empty=True`, all five dims set to NaN, `parse_error` populated with the reason.

**Headline policy is single-sourced in `leaderboard.HEADLINE_DIMS`.** `evaluator.score_response` is now parse-only — it returns the five raw dim scores plus telemetry but does **not** compute `overall_applicable`. Per-row headline mean = `np.nanmean([factuality, reasoning, instruction_following, verbosity])`, computed at aggregation time. The old dual-computation drift source (one in `evaluator.py`, one in `leaderboard.py`) is eliminated.

`overall_strict` (also in `leaderboard.py`): per row, each NaN **headline** dim is imputed with that model's own mean for that dim across all rows, then averaged. `format_compliance` is not part of the strict mean either.

**Empty-judge fix.** Previously, an empty judge response left `instruction_following` and `format_compliance` at 0.0 defaults while NaN-ing the other two — silently underscoring models. Current behaviour: ALL FIVE dims become NaN and `judge_empty=True` is recorded on the row, so those rows can be filtered, counted (`n_judge_empty` per model on the leaderboard), or imputed by the strict aggregator.

Parquet schema v2 (24 columns — old v1 rows are NOT migrated):
```
prompt_id str | model str
factuality f64 | reasoning f64 | instruction_following f64 | format_compliance f64 | verbosity f64
judge_empty bool | fallback_triggered bool | retry_count i32
latency_ms i64 | tokens_used i64 | cost_usd f64 (always 0.0 on :free)
provider str ("openrouter") | day_of_run i32 | difficulty str
judge_model str | parse_error str | judge_latency_ms i64 | judge_tokens_used i64
response_text str (capped 20k chars) | response_truncated bool | gt_provided bool | rubric_version i32
```

Fields removed vs prior (v1, 20-col) schema: `overall_applicable` (no longer persisted at row time; computed only at aggregation). Added in v1→v2 (this revision): `verbosity`, `difficulty`. Added in v2 schema (this revision, grounded-judging): `response_text`, `response_truncated`, `gt_provided`, `rubric_version`. The `difficulty` value is read from `prompt_suite.json` at row construction; `rubric_version` is stamped from `config.llm.RUBRIC_VERSION` on every row.

**Mixed-schema guard.** `data/rows/` currently holds 1,800 v1 rows (no `rubric_version` column) from the published run. `batch_eval.main()` calls `check_row_schema_guard()` at startup, which refuses to run (prints a banner, exits nonzero, writes nothing) if any row file predates the current `RUBRIC_VERSION` — old rows are never auto-migrated or auto-deleted; the operator must archive them first (`mkdir data/_archive_v1_rows && move data\rows\*.parquet data\_archive_v1_rows\`). `consolidate_rows_to_parquet()` also asserts uniform schema across row files before concatenating, as a second line of defense. `leaderboard.load_results()` asserts a single unique `rubric_version` in `eval_results.csv` — v1 (ungrounded) and v2 (grounded) factuality scores are not comparable and must never be aggregated together.

Leaderboard aggregation (`leaderboard.compute_leaderboard`):
- Group by `model`; per-dimension means (`avg_<dim>`, five entries) via `pd.Series.mean(skipna=True)`.
- `overall_applicable`: row-wise nanmean over `HEADLINE_DIMS`, then column mean.
- `overall_strict`: per-row impute-then-average over `HEADLINE_DIMS` using each model's own dim means.
- `ci_low` / `ci_high`: 95% bootstrap CI on the new 4-dim `overall_applicable` — 1000 resamples, seed 42, pure numpy. Sanity-checked in `tests/test_scoring.py`.
- `latency_p50_ms`, `latency_p95_ms`, `avg_tokens_used`, `total_cost_usd`, `avg_cost_per_prompt_usd`, `score_per_dollar` (numeric or `"N/A (free tier)"`).
- `cat_<category>` per category, joined via `prompts/prompt_suite.json`. Six categories: `factual_recall`, `multi_step_reasoning`, `instruction_following`, `code_generation`, `safety_calibration`, `hallucination_under_uncertainty`. `adversarial_edge_cases` dropped.
- Diagnostics: `n_judge_empty`, `n_fallback`, `n_prompts`.
- Sorted desc by `overall_applicable`, ranked 1..N.

**Stratified output (`compute_leaderboard_by_difficulty`)** — one row per `(model × difficulty)` tier, columns `model, difficulty, overall_applicable, n_prompts, avg_<5 dims>`. Same headline policy. Emitted to `data/leaderboard_by_difficulty.csv` and ordered easy → expert. Skipped when input rows have no `difficulty` column (legacy data).

**Auto-publish (`_publish_to_public`)** — at the end of `leaderboard.main()`, both CSVs are copied into `public/data/` when that directory exists (no-op on backend-only checkouts). This wires the frontend without a separate manual copy step.

## 5. FRONTEND

Routes (src/App.tsx):

| Route | Lazy import | File |
|---|---|---|
| `/` | `Overview` | src/components/pages/Overview.tsx |
| `/rankings` | `Rankings` | src/components/pages/Rankings.tsx |
| `/dimensions` | `Dimensions` | src/components/pages/Dimensions.tsx |
| `/methods` | `Methods` | src/components/pages/Methods.tsx |
| `/blog` | `Blog` | src/components/pages/Blog.tsx |

Wrapped in `<PageFrame>` + `<AnimatePresence>` (motion). Suspense fallback `null`. Navbar items match the route list — five tabs (Overview / Rankings / Dimensions / Methods / Blog). `<Analytics />` from `@vercel/analytics/react` is mounted at the root of `App.tsx` (sibling to `<AnimatePresence>`, inside `<PageFrame>`) for production pageview telemetry on Vercel.

Layout components: `PageFrame`, `Navbar` (mobile collapses to hamburger), `BottomLeft`, `BottomRight`, `CtaButton`, `ExpandableViz`, `GrainOverlay`, `ScrollableZone`, `ScrollToTop` (mobile-only FAB mounted inside `ScrollableZone`).

Chart components (active): `LeaderboardTable`, `PerformanceLatencyScatter`, `DifficultyBreakdown` (Rankings); `RadarComparison`, `DimensionDeepDive` (Dimensions).

Data loading (src/lib/loadCsv.ts):
- `loadLeaderboard()` fetches `/data/leaderboard.csv`, papaparse with `header:true, dynamicTyping:true, skipEmptyLines:true`. A `mapRow()` step maps the full CSV schema onto `ModelPerformance` — `rank`, `overall_applicable` → `overallScore`, `overall_strict`, `ci_low`/`ci_high`, every `avg_<dim>` including the new `avg_verbosity`, `avg_cost_per_prompt_usd`, **`latency_p50_ms`/`latency_p95_ms` (kept in ms — no `/1000`)**, `n_prompts`/`n_judge_empty`/`n_fallback`, and the six `cat_*` columns (`cat_safety_calibration` + `cat_hallucination_under_uncertainty` replace `cat_adversarial_edge_cases`). Rows missing `overall_applicable` are dropped. Returns `FALLBACK_DATA` only if zero rows survive mapping.
- `loadLeaderboardByDifficulty()` fetches `/data/leaderboard_by_difficulty.csv` and maps each row onto `ModelDifficultyRow` (`model`, `difficulty`, `overallScore`, the five `avg_<dim>` fields, `nPrompts`). Returns `[]` on miss — the consuming chart unmounts cleanly.
- `loadEvalResults()` is an alias of `loadLeaderboard`.
- `loadDimensions()` returns the hard-coded list `["Factuality", "Reasoning", "Instruction Following", "Format Compliance", "Verbosity"]`.
- `FALLBACK_DATA` carries placeholder rows in the new 5-dim / 6-category shape. Real values populate after the first eval run + `leaderboard.py` mirrors the CSVs into `public/data/`.

Color registry (src/lib/modelColors.ts):
- `buildModelColors(models)` returns a `Map<model, hex>` using **family-based assignment** matched against the model id prefix: Google → `#4285F4`, OpenAI → `#10A37F`, Anthropic → `#D97757`, Moonshot → `#A855F7`, Meta-Llama → `#6366F1`, Mistral → `#F97316`, DeepSeek → `#06B6D4`, Qwen → `#EC4899`, xAI → `#E11D48`, Cohere → `#EAB308`. Unknown families fall through a bright distinct palette by encounter order. The same registry feeds the scatter, the table's expanded category bars, the deep-dive bars, and the radar — so a given model's color is identical across every chart on the dashboard.
- `modelDisplayName(model)` strips the `:free` suffix and the `<provider>/` prefix (`"moonshotai/kimi-k2.6:free"` → `"kimi-k2.6"`); full id is preserved in HTML `title` tooltips wherever a display name is shown.

`ModelPerformance` (src/types/index.ts) is the complete projection of the headline CSV: `rank`, `model`, `overallScore` (= `overall_applicable`), `overallStrict?`, `ciLow?`, `ciHigh?`, five `avg_<dim>` fields (`factuality`, `reasoning`, `instructionFollowing`, `formatCompliance`, `verbosity`), `costPerPrompt`, `latencyP50Ms`/`latencyP95Ms` (milliseconds), `nPrompts`/`nJudgeEmpty`/`nFallback`, and six `cat*` fields (`catFactualRecall`, `catMultiStepReasoning`, `catInstructionFollowing`, `catCodeGeneration`, `catSafetyCalibration`, `catHallucinationUnderUncertainty`). `ModelDifficultyRow` is the row shape of the by-difficulty CSV: `model`, `difficulty` (`"easy" | "medium" | "hard" | "expert"`), `overallScore`, the five `avg_<dim>` fields, `nPrompts`. No dead fields; no aliases.

Rankings page (src/components/pages/Rankings.tsx):
- `LeaderboardTable` renders 12 columns: Rank · Model · Overall (with the 95% CI bracket `[lo – hi]` rendered in muted text beneath the score) · Factuality · Reasoning · Instruct · Format · Verbosity · Latency P50 (`<int>ms`) · Prompts · Fallbacks. Best-in-column values are underlined; the Format column is included for reporting but does *not* feed `Overall` — the table footer explains the 4-dim headline policy explicitly. Each row has a chevron expander that opens a detail panel showing `overall_strict` and a horizontal mini bar chart of the six `cat_*` scores, color-keyed to the same model color.
- `PerformanceLatencyScatter` sits directly below the table. Unchanged in this revision — recharts `ScatterChart` with `latencyP50Ms` on x (tick formatter shows seconds) and `overallScore` on y, ZAxis sizing dots by `nPrompts`, asymmetric ErrorBars (CI vertical + p50→p95 horizontal), custom top-right legend overlay.
- `DifficultyBreakdown` sits below the scatter. Grouped recharts `BarChart` with x = difficulty tier (easy / medium / hard / expert), one bar per model per tier, fed by `loadLeaderboardByDifficulty()`. Uses the shared `buildModelColors()` registry so colours line up with the table, scatter, and Dimensions charts. The chart is the lens that surfaces model separation at the expert tier, which the headline mean averages out across all 600 prompts.

Dimensions page (src/components/pages/Dimensions.tsx):
- `RadarComparison` (left) — **5-axis radar** (Factuality / Reasoning / Instruct / Format / Verbosity) per model, domain `[60, 100]`, fills via the shared color registry, legend uses display names. All five dims appear on the radar for completeness; the headline-vs-non-headline distinction is a Rankings/Methods concern.
- `DimensionDeepDive` (right) — dropdown selects one of five dimensions (`keyMap` now includes Verbosity); horizontal bar chart sorted desc; YAxis width 180px (no clipping of long ids), domain `[0, 100]` with explicit numeric `LabelList` at each bar's right edge so differences are visible regardless of axis range; bar colors come from the model-color registry; tooltip shows the full id.
- Both Dimensions cards use **explicit pixel heights** (`h-[320px]` / `h-[340px]`) on the chart wrapper. recharts `ResponsiveContainer` measures parent `clientHeight` synchronously; a `flex-1` parent inside a `flex flex-col` grid cell can resolve to `0` on first paint, which silently hides the chart. Pixel heights avoid that path.

Stack (package.json): React 19, react-dom 19, react-router-dom 7, Vite 6, TypeScript 5.8, Tailwind 4 + `@tailwindcss/vite`, Recharts 3, motion 12, papaparse 5, shadcn primitives (radix-ui slot), lucide + hugeicons, `@vercel/analytics`.

Dev: `npm run dev` → `vite --port=3000 --host=0.0.0.0`. Build: `vite build`. Lint: `tsc --noEmit`.

## 6. DEPLOYMENT

| Target | What | How |
|---|---|---|
| Vercel | React static site | GitHub-integrated. `vercel.json` rewrites every path to `/index.html` so React Router handles direct nav. Runtime fetch of `/data/leaderboard.csv` and `/data/leaderboard_by_difficulty.csv` — both auto-mirrored into `public/data/` by `leaderboard.py._publish_to_public()`. `@vercel/analytics` is wired at the App root. **Auto-deploy off `main` is currently gated** via `vercel.json` `"git": {"deploymentEnabled": {"main": false}}` — pushes to `main` are ignored by Vercel until the flag is flipped back to `true`. This gates the in-flight 5-dim revision so the deployed site keeps the prior schema until the multi-day eval run completes and the new CSVs are validated. To re-enable: change `false` → `true`, commit, push. |
| Local Windows | Python eval harness | `python batch_eval.py [-y]`. In-process quota-sleep loop survives reset boundary; no external scheduler. New status-display blocks (quota-exhausted box, wake-tick heartbeat, resume banner, completion box) print to stdout — see §3.6. A bounded patient multi-pass sweep (§3.8) auto-retries transient-429 tails with widening inter-pass gaps, so a single invocation drives the remainder to completion without manual re-runs. |

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

Pending items:

- **Grounded judging + schema v2 implemented, re-run pending (this revision).** `data/rows/` still holds the 1,800 v1 rows behind the published leaderboard; the next `batch_eval.py` run will refuse to start until they're archived (see §4 "Mixed-schema guard"). Code + tests only this revision — 54/54 tests pass, zero API calls, published CSVs/`public/data/` untouched. Once a v2 run completes, the published leaderboard needs a deliberate re-run + redeploy (grounded factuality scores are not comparable to v1).
- **Redeploy production**: the full 1800-pair run is complete and `leaderboard.py` has been re-run (both CSVs + `public/data/` mirror refreshed to the 5-dim / 600-prompt / 3-evaluator set). The **only** remaining step is re-enabling Vercel auto-deploy — flip `vercel.json` `git.deploymentEnabled.main` from `false` → `true`, commit, and push so production picks up the new schema and data (see §6).
- **Calibration probes not yet run for real.** `calibration_probes.py` is implemented and tested (`--dry-run` verified end-to-end offline), but the real 96-call pass against the nvidia judge (burns ~96 of its 300 RPD) has not been executed — needs explicit approval per session. Until it runs, `data/judge_calibration.csv` doesn't exist and Methods still shows the "planned" fallback sentence.
- **Second judge not yet run for real (blocked on the v2 re-run above).** `second_judge.py` is implemented and tested but requires `data/eval_results.parquet` to be schema-v2 (it exits nonzero against the current v1 parquet — verified) — so it can't run until `batch_eval.py` is re-run under schema v2. Once that happens, run `python second_judge.py --yes` (300 calls, ~350 RPD on the new `poolside` leaf, needs explicit approval) to produce `data/judge_agreement.csv`; Methods and the README limitation bullet stay on their "not yet run" text until then.
- **HTB provider weights are still hand-set, not learned.** `_PROVIDER_RATES` was rebalanced this revision (see "Resolved" below for the math); the weekly recompute against `failed_calls.json` + parquet success-rate logs is still not automated. Re-tune by hand if a run shows one eval lane binding materially earlier than the others.
- **Smoke verification only**: tests use mocked OpenAI clients (zero real API calls). End-to-end verification against live OpenRouter is deferred — it burns RPD and requires explicit approval per session.

Resolved since the prior revision (no longer gaps):

- **Transient-429 tail no longer requires manual re-runs.** A ~4% tail (67/1800) of pairs — mostly `kimi-k2.6` evals whose only fallback `gemma-4-26b` lands on an also-throttled `google` leaf — was stuck on *transient* upstream 429s (`"…temporarily rate-limited upstream"`, **not** the `free-models-per-day` daily cap, and HTB budgets were nowhere near exhausted). Such errors don't trigger the §3.6 quota-sleep/requeue; they're logged to `failed_calls.json` and dropped, and a single immediate re-run hits the same instantaneous throttle. Fix (confined to `batch_eval.main` — no architecture change): a bounded patient multi-pass sweep that recomputes the still-missing pairs from disk after each pass and re-runs the existing orchestrator over the remainder with widening inter-pass gaps (5/15/30 min, 4 passes max) so the upstream throttle can clear. See §3.8. 36/36 tests still pass. **The tail is now fully drained — all 1800 pairs are evaluated and `leaderboard.py` has been re-run over the complete set; only the production redeploy remains (see Pending items above).**
- **Consolidation no longer bloats the parquet.** `consolidate_rows_to_parquet()` previously re-read the existing `eval_results.parquet` *and* re-appended all per-row files on every run, with no de-dup — so each consolidation grew the file by ~one full pass. A real 1,800-pair run had ballooned to **10,624 rows** across `day_of_run` 1–4, which inflated `n_prompts` to ~3,500/model and artificially tightened the bootstrap CIs (resampling over ~6× the true sample). Fix: rebuild from `ROWS_DIR` only (the canonical latest-per-pair checkpoints) plus a defensive `(prompt_id, model)` de-dup, so consolidation is now idempotent at exactly 1,800 rows. The published CSVs were regenerated from the rebuilt parquet. 36/36 tests still pass.
- Empty-judge handling now NaN-s all four dims and sets `judge_empty=True` — matches the original intent.
- `eval_state.json` no longer carries `pending_evals` / `last_exhausted` / `next_run_utc`; the in-process quota-sleep loop replaces the `schtasks` round-trip.
- Per-provider 4.0s gap + 18-RPM sliding window superseded by the HTB tree.
- `tests/` directory exists — 36 mocked tests cover HTB, DRR, scoring, fallback, and retry mechanics.
- **Full 1800-pair run completed** — all 600 prompts × 3 evaluators are evaluated; the patient multi-pass sweep drained the transient-429 tail (see entry above). `data/eval_results.csv` holds the complete set and `leaderboard.py` has been re-run, refreshing both CSVs and the `public/data/` mirror. (Supersedes the earlier first-600 milestone.)
- **Stale-row leak fixed** — `load_completed_pairs()` and `consolidate_rows_to_parquet()` now filter by current `EVALUATOR_MODELS` via `pyarrow.compute.is_in`. Surfaced when 16 prior-roster `deepseek/*` rows in `data/rows/` were silently consolidated into the leaderboard as a ghost lane with all-1.0 dim scores (from fallback-hop responses recorded under the requested model id).
- **`Blog.tsx` model-cards revision** — 4 compound cards (Judge + 3 Evaluators) with role badges, provider glyphs (simple-icons SVG for OpenAI/Google/NVIDIA, monogram for MoonshotAI), architecture-type pill (MoE/Dense/Hybrid/LatentMoE), and click-to-expand inline fallbacks. Section 04 rewritten around HTB + DRR with an inline ASCII tree; Section 05 updated to the new `overall_applicable`/`overall_strict`/`ci_low`/`ci_high`/`n_judge_empty`/`n_fallback` schema; Section 07 evaluator roster corrected; new "Traffic Shaping the Free Tier" pitch section inserted between header and Section 01.
- **`Blog.tsx` retention pass** — header subtitle replaced with a fact hook (`1,200 / 4 / 1996 / 2002 / $0`); pitch section reordered to lead with the "traffic shaping, not rate-limit accounting" thesis, gains an inline SVG HTB tree (leaf widths ∝ RPD share) and a `tc-htb on API quota` chip-led callout that surfaces the `$0` total. Section 03 collapses the full judge rubric behind a `CollapsiblePre` expander, promotes the Gemma 4 31B dual-role line to a visible amber sentence, and tightens the GPT-OSS cross-ref label to `(↑ see card above)`. Section 04 cards 3–5 (Retry / Atomic / Self-Pacing) collapse into one compact label-plus-body strip to break the five-card rhythm. Section 05 leads with a one-line "why two aggregates" sentence and collapses the four `avg_<dim>` cells into one. Section 06 converts to a 3-column "Blog post (strikethrough) vs Benchmark" grid. Footer replaced with a centered `$0 · 1,200 · 2,400 · 0` metric strip. Section 07 left untouched. `tsc --noEmit` clean.
- **Frontend schema wired to new CSV** — `src/lib/loadCsv.ts` now maps `overall_applicable`/`overall_strict`/`ci_low`/`ci_high`/`avg_<dim>`/`avg_cost_per_prompt_usd`/`latency_p50_ms` (ms→s) onto `ModelPerformance`. `ModelPerformance` gained optional `overallStrict`/`ciLow`/`ciHigh`. `FALLBACK_DATA` replaced with real free-tier evaluator rows from the latest run. `tsc --noEmit` clean. Rankings/Dimensions/Frontier render real data (all four chart components — `LeaderboardTable`, `RadarComparison`, `DimensionDeepDive`, `CostQualityScatter` — pull from the same `loadLeaderboard()` and share the field-name layer, so no chart-component edits were needed).
- **`public/data/leaderboard.csv` present** — copied from `data/leaderboard.csv` after the first full run; production fetch of `/data/leaderboard.csv` no longer 404s.
- **Rankings rebuilt around the full CSV signal.** `LeaderboardTable` now renders Rank · Model · Overall + 95% CI bracket · 4 dimensions · Latency (ms) · Prompts · Fallbacks, with chevron-expandable rows surfacing `overall_strict` and a per-row category bar chart of the five `cat_*` scores. Cost column dropped (always `0` on `:free`). `PerformanceLatencyScatter` added beneath the table — recharts ScatterChart with vertical CI error bars, horizontal p50→p95 latency error bars, ZAxis sizing dots by `nPrompts`, and a custom top-right "MODELS" legend overlay. `ModelPerformance` expanded to a full CSV projection (rank, p50/p95 in ms, prompt counts, all five `cat_*`); `latency` no longer divided by 1000 at load time.
- **Frontier page fully removed.** `/frontier` route, `Frontier.tsx`, and `CostQualityScatter.tsx` all deleted from disk; navbar is five items (Overview / Rankings / Dimensions / Methods / Blog). Free-tier evaluation makes the cost axis identically zero, which is why the page was cut. (Earlier revision kept the files on disk as DEPRECATED — that hold is over.)
- **Methods page rebuilt as "Why You Should Believe This."** Five cards: (1) Scoring Rubric — renders `JUDGE_SYSTEM_PROMPT` from `config/llm.py` verbatim in a `<pre>` block with judge model id (`stripFree(JUDGE_MODEL)`) above and a 6-row Score → Meaning table below; (2) Infrastructure — opens with the OpenRouter free-tier framing, ASCII HTB tree, and four stat lines derived from `prompt_suite.json` (`totalPrompts * 3 = pairs`, `*2 = logical calls`); (3) Statistical Validity — bootstrap 95% CI, `overall_applicable` vs `overall_strict` definitions, judge-calibration honest gap; (4) Known Limitations — five specific items (single-judge bias, no human validation, truncation, free-tier availability, Gemma 4 31B dual role); (5) Prompt Categories — table rendered dynamically from `import promptSuite from "../../../prompts/prompt_suite.json"` with `snake_case → Title Case` transform and a derived Total row. `JUDGE_MODEL` and `JUDGE_SYSTEM_PROMPT` are mirrored as TS constants at the top of `Methods.tsx` with a `// Mirror of config/llm.py — keep in sync.` comment (Python source isn't importable from the frontend). Old "Evaluation Dimensions" + "Scoring Approach" cards removed; the stale "Gemini 2.0 Flash" judge reference is gone. `BottomRight` tagline updated.
- **Mobile-compatibility pass.** Desktop layouts unchanged; every override gated on `sm:`/`md:` so render is pixel-identical above 768 px. New: `src/lib/useIsMobile.ts` (one-line `matchMedia('(max-width: 640px)')` hook with `useSyncExternalStore`-style subscribe via `useEffect`), `src/components/layout/ScrollToTop.tsx` (mobile-only FAB at `bottom-4 left-4`, appears after 200 px scroll, attaches to `ScrollableZone`'s scroll container via a forwarded ref; needs `pointer-events-auto` explicitly because the wrapper carries `pointer-events-none`). `Navbar` splits into a desktop pill (`hidden md:flex`) and a mobile hamburger bar (`md:hidden`, right-aligned button, no brand wordmark — desktop has none either, and the duplicate clashed with the Overview hero). `BottomLeft` non-overview is `hidden md:block` (page name already in navbar). `BottomRight` overview branch repositions to `top-[68px] right-4` on mobile (under the navbar) to stop colliding with the Overview hero wordmark at bottom-left; non-overview branch stacks text-above-CTA on mobile. `ExpandableViz` drops the mobile-inverted `scale-[1.1]`, expand button is 44 px and visible on touch (`opacity-70 md:opacity-0`). `LeaderboardTable` `min-w-[920px]` → `min-w-[520px] md:min-w-[920px]` with per-dimension columns `hidden sm:table-cell` and Latency/Prompts/Fallbacks `hidden md:table-cell`. `RadarComparison` shrinks `outerRadius` to `68%` and fonts on mobile; `DimensionDeepDive` Y-axis width drops `180 → 96`; `PerformanceLatencyScatter` floating legend is `hidden md:flex`, with a flex-wrap inline legend rendered below the chart on mobile. `Blog.tsx` grids gain a `grid-cols-1` baseline (`grid-cols-2 md:grid-cols-3` → `grid-cols-1 sm:grid-cols-2 md:grid-cols-3`); HTB SVG wraps in `overflow-x-auto` with `min-w-[440px]`; the prompt-taxonomy table drops the "What it stresses" column under `sm:`. `index.html` viewport gets `viewport-fit=cover` + `theme-color`. `src/index.css` adds a global `prefers-reduced-motion` block that flattens animations/transitions.
- **Family-based model-color registry.** New `src/lib/modelColors.ts` maps each model id to a deterministic color by provider family (Google → blue, OpenAI → green, Anthropic → orange, Moonshot → violet, Meta → indigo, Mistral → orange-red, DeepSeek → cyan, Qwen → magenta, xAI → rose, Cohere → amber; unknown families fall through a bright distinct palette). `buildModelColors(models)` returns the resolved `Map`, consumed identically by the scatter, the table's expanded category bars, the deep-dive bars, and the radar. Replaces the prior three-color cycling array used independently in each chart.
- **Dimensions page placeholder content cut + label-clipping fixed.** `DimensionDeepDive` no longer renders the hardcoded "Sample Completions" cards (no per-prompt response data exists in the pipeline). YAxis width widened from 100→180px so long ids like `moonshotai/kimi-k2.6:free` aren't clipped; display name shown on the axis with full id in the tooltip. Domain switched from `[50, 100]` to `[0, 100]` with explicit numeric `LabelList` at each bar's right edge so score differences are visible regardless of axis range. Both Dimensions cards use explicit pixel heights on the chart wrapper (`h-[320px]` / `h-[340px]`) — `flex-1` inside the page's `flex flex-col` grid cell caused recharts' `ResponsiveContainer` to read `clientHeight: 0` and render nothing on first paint.
- **5-dim rubric + 600-prompt suite + difficulty stratification (this revision).** `verbosity` promoted to a first-class judge dimension; `format_compliance` still scored on every prompt and reported as `avg_format_compliance` but excluded from the headline mean. Headline policy single-sourced in `leaderboard.HEADLINE_DIMS`; `evaluator.score_response` is parse-only (no row-level `overall_applicable`). Prompt suite expanded from 200 / 5 cats / 40 each to **600 / 6 cats / 100 each**, with every prompt tagged `easy | medium | hard | expert` at 15/25/35/25 per category (strict validator in `generate_prompts.py`). `adversarial_edge_cases` dropped; `safety_calibration` (bidirectional over/under-refusal) and `hallucination_under_uncertainty` (false-premise / fabrication bait) added. Parquet schema: +`verbosity`, +`difficulty`, −`overall_applicable` (20 columns). New `data/leaderboard_by_difficulty.csv` exposes per-(model × tier) separation; `_publish_to_public()` mirrors both CSVs into `public/data/`. `batch_eval.py` gains a quota-exhausted status box (printed once on entry), 5-min wake-tick heartbeat, resume banner (`day_of_run` bump on natural wake), completion box, and clean Ctrl+C exit — scheduler wired via optional `on_quota_{enter,tick,resume}` callbacks; no scheduling or timing changes. Judge prompt gains a one-line note: correctly identifying a false-premise or unanswerable request as such is the high-scoring response. Frontend: `ModelPerformance` gains `verbosity` + cat swap; new `ModelDifficultyRow` + `loadLeaderboardByDifficulty()`; Radar 5 axes; `DimensionDeepDive` adds Verbosity; `LeaderboardTable` adds Verbosity column + cat swap + new 4-dim headline footer; new `DifficultyBreakdown` chart on Rankings. Methods mirrors the new 5-dim judge prompt char-for-char with `config/llm.py`; Blog drops three stale "deterministic parser" false-claim sites (lines 512, 540, 832) and bumps 200 → 600 in copy. 25/25 tests pass; `tsc --noEmit` clean. Auto-deploy on Vercel is gated off `main` via `vercel.json` `git.deploymentEnabled.main:false` so the in-flight revision can be pushed without redeploying production until the eval completes.
- **429-throttling collapse on day one** (was: <200 of 1800 pairs completed before the daily quota drained, with heavy EVAL/JUDGE FAIL output). Root cause: the retry path used a fixed `[30, 90]`s no-jitter schedule, ignored the server's `Retry-After` / `X-RateLimit-Reset` header, retried *every* error class (including non-retryable 4xx), and a `_NODE_BURST=5` allowed brief >20 RPM bursts. Because OpenRouter counts failed 429s against the 1000/day free quota, each blind, badly-timed retry permanently burned a quota unit — so the day's budget drained on wasted attempts long before useful work completed. Fix (confined to `config/llm.py`, retry mechanics only — HTB accounting, DRR, scheduler, batch_eval, scoring, and frontend all untouched): honor `Retry-After`/`X-RateLimit-Reset` then full-jitter exponential backoff (`_retry_after_seconds` / `_compute_backoff`); `is_retryable()` retries only 429/5xx/timeouts and fails 4xx + empty-choices fast straight to the fallback hop; `_NODE_BURST` 5 → 2 to stay under the 20 RPM ceiling; `MAX_RETRY` stays 3. Daily debit-per-attempt is deliberately **kept** (it correctly mirrors the server's 429-counting). All market-standard techniques (OpenAI cookbook / Anthropic + Google SDKs); no novel algorithm. 36/36 mocked tests pass (new `tests/test_retry.py`). Throughput ceiling is unchanged — 3600 calls on a 1000/day cap is inherently multi-day, handled by the existing quota-sleep; the fix converts wasted 429 retries into completed pairs.
- **Eval-budget mis-allocation under current model layout** (was: openai 488 / moonshotai 81 / google 81 RPD). Root cause: `_PROVIDER_RATES` carried the 0.15-vs-0.025 prior from a layout where `openai/*` hosted **two** primary evaluators (`gpt-oss-20b` + `gpt-oss-120b`) on a shared provider lane, and small open-weight providers were prior-flagged as flaky. Current `EVALUATOR_MODELS` is one model per provider (`kimi-k2.6` on moonshotai, `gemma-4-31b-it` on google, `gpt-oss-120b` on openai), so the 6× openai skew left moonshotai/google binding hard (~81 RPD vs ~158 needed/day) while openai sat on +330 RPD of unused budget. Rate side wasn't load-bearing — every leaf's `ceil_per_sec` equals the root rate, so leaves fully borrow; weights only affected `_split_eval_budget()`. Fix applied: `_PROVIDER_RATES = {nvidia: 0.10, openai: 0.05, moonshotai: 0.05, google: 0.10}` — equal across the two non-fallback-receiving eval lanes, double weight for google since two other lanes' fallback hops (kimi → gemma-4-26b, gpt-oss-120b → gemma-4-31b) land on its leaf. New eval split: openai 163 / moonshotai 163 / google 325 RPD. Judge (nvidia 300 RPD) unchanged.
- **Judge calibration probes implemented (this revision).** `evaluator.score_response`'s inline fence-stripping/JSON-parsing logic extracted into a standalone `parse_judge_json(raw_text) -> (scores, parse_error)` in `evaluator.py`, called by both `score_response` and the new runner — bit-identical behavior confirmed against the pre-existing scoring tests. New `prompts/calibration_probes.json`: 32 fixed (prompt, response) anchor pairs — 6 per dimension (2 top-band / 2 mid-band / 2 bottom-band, bands are ranges over the rubric's discrete anchors, never point targets) × 5 dims, plus 2 null-semantics probes (`expect_null`) that assert the judge returns `null`, not a low score, when a dimension doesn't apply. New `calibration_probes.py`: calls the judge `JUDGE_MODEL`/`JUDGE_SYSTEM_PROMPT` (imported from `config.llm`, never copied) 3× per probe with the exact production truncation slices, writes `data/calibration_runs.csv` (one row per probe×run) and `data/judge_calibration.csv` (one row per dimension: `n_probes`, `n_runs`, `band_hit_rate`, `mae_vs_band_midpoint`, `test_retest_std`, `n_parse_failures`, `n_fallback_scored`). Parse failures always count as reliability failures (never dropped, never silently treated as a band hit even when a resulting NaN happens to satisfy a null-check). Rows scored by the fallback judge model (`nemotron-3-nano-30b-a3b`, not the primary) are excluded from headline stats and counted separately in `n_fallback_scored`, since a fallback-scored probe measures a different judge. `--dry-run` runs fully offline against a mocked client + an isolated HTB tree (ample tokens/budget, never touches the real process-global daily counters) — verified end-to-end. Real runs require `--yes` and are hard-capped: refuses to proceed if `32 × REPEATS=3 = 96` calls would exceed nvidia's 300 RPD judge budget. `leaderboard.py._publish_to_public()` now also mirrors `data/judge_calibration.csv` into `public/data/` when present (no-op otherwise). Frontend: new `JudgeCalibrationRow` type, `loadJudgeCalibration()` in `loadCsv.ts` (returns `[]` on any fetch/parse failure, same pattern as `loadLeaderboardByDifficulty`), and the Methods "Judge Calibration" card now renders a live Dimension / Band-hit / Test–retest σ table when the CSV is present, falling back to the original "planned but not yet implemented" sentence when it isn't — verified visually in both states via a headless-browser screenshot. New `tests/test_calibration.py` (9 tests, all mocked). 45/45 tests pass; `tsc --noEmit` clean. The real 96-call probe pass has **not** been run yet (see Pending items above) — `data/judge_calibration.csv` does not exist in this revision.
- **Second-judge agreement sampling implemented (this revision, code + tests only — no API calls, no re-run).** Converts the README's "single judge — same-family bias is possible" limitation into a measured artifact. `evaluator.py`'s inline judge-message construction extracted into `build_judge_user_message(prompt_obj, response_text) -> (str, bool)`, used by both `score_response` and the new `second_judge.py` so a second judge re-scores byte-identical input to judge 1 (disagreement then measures judge bias, not prompt drift). New second judge lane in `config/llm.py`: `JUDGE2_MODEL="poolside/laguna-m.1:free"`, `JUDGE2_FALLBACK="poolside/laguna-s-2.1:free"` — Poolside chosen after checking OpenRouter's live `:free` roster found no Qwen/DeepSeek/Llama free model available (the plan's preferred picks), and Poolside was the best remaining option with a same-family fallback (one new HTB leaf, not two); `call_model`'s `role` gained a third literal, `"judge2"`. New `second_judge.py`: refuses to run against pre-v2 parquet (verified nonzero exit against the current v1 data); deterministic stratified sampling (`md5(f"{prompt_id}|{model}") mod 6 == 0`, truncated/extended to exactly 100 pairs per evaluator model — no RNG, byte-identical across re-runs/resumes); per-pair checkpointing to `data/judge2_rows/*.parquet` (same tmp→fsync→`os.replace` idiom as `batch_eval.py`) with resume; aggregation to `data/judge_agreement.csv` (one row per dimension + one `overall` row: `n`, `pearson_r` (empty string when either side has zero variance), `mae`, `pct_within_one_step` (±0.25), `n_judge1_nan_judge2_val`/`n_judge2_nan_judge1_val` (null-disagreement, kept separate from magnitude stats), `n_fallback_scored` (excluded from headline agreement stats)). Never blended into the leaderboard — a runtime hash-guard in `second_judge.main()` aborts if any leaderboard CSV changes during the run. `leaderboard.py._publish_to_public()` now also mirrors `data/judge_agreement.csv` when present. Frontend: new `JudgeAgreementRow` type, `loadJudgeAgreement()` in `loadCsv.ts`, and a new "Inter-Judge Agreement" block on Methods (renders the table when the CSV exists, else a placeholder sentence); the "Single judge model" Known-Limitations bullet becomes conditional on the same data. New `tests/test_second_judge.py` (20 tests, all mocked) plus a budget-constant fix in `test_htb.py` for the new 1300 RPD total. 74/74 tests pass; `tsc --noEmit` clean. `data/`, `public/data/` untouched — the published leaderboard is still v1 and unaffected.
- **Grounded judging + parquet schema v2 (this revision, code + tests only — no API calls, no re-run).** Fixes three validity holes found by inspection ahead of the next eval run: (1) the judge previously never saw `ground_truth` — factuality was judged blind from the judge's own parametric knowledge, which is circular for `hallucination_under_uncertainty`; `score_response` now sends a `Reference (ground truth for factuality grounding): …` line before the Response whenever `prompt_obj["ground_truth"]` is non-empty, omitted entirely otherwise (never sent empty), and `RUBRIC_VERSION=2`'s rubric paragraph teaches `decline_or_flag:`-prefixed references correctly so honest declines don't score as factually wrong. (2) response/prompt truncation was two bare magic-number slices (`[:1500]`, `[:500]`); now named constants `evaluator.JUDGE_RESPONSE_MAX_CHARS=4000`/`JUDGE_PROMPT_MAX_CHARS=1500`/`GROUND_TRUTH_MAX_CHARS=800`, with a `response_truncated` flag persisted per row. (3) response text was never persisted anywhere, blocking re-judging, qualitative analysis, and a future per-prompt explorer; `_SCHEMA` gains `response_text` (capped `batch_eval.STORE_RESPONSE_MAX_CHARS=20_000` — a separate decision from the judge-input cap), `response_truncated`, `gt_provided`, `rubric_version` (24 columns total). `batch_eval.check_row_schema_guard()` refuses to start (banner + nonzero exit + no writes) while any pre-v2 row file remains in `data/rows/` — verified against the real 1,800 v1 files; `consolidate_rows_to_parquet()` adds a second-line-of-defense schema-uniformity assert; `leaderboard.load_results()` now asserts a single unique `rubric_version` so v1/v2 scores can never silently mix in one aggregation. `Methods.tsx`'s `JUDGE_SYSTEM_PROMPT` mirror updated and confirmed byte-for-byte identical to `config/llm.py` (backtick in the new rubric text needed escaping in the TS template literal). README's truncation limitation bullet annotated `(fixed in pipeline v2 … pending re-run)`. 54/54 tests pass (8 new); `tsc --noEmit` clean; `data/`, `public/` untouched — the published leaderboard is still v1 until a deliberate re-run.
