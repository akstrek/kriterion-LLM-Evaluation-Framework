P6 — Kriterion: Build Summary
What It Is
LLM evaluation harness scoring three open-weight evaluator models across 200 prompts on four research dimensions, judged by an architecturally independent model. Published as a React dashboard with an accompanying blog post.
Model Configuration
Evaluators (via OpenRouter free tier):

OpenAI GPT-OSS 120B (openai/gpt-oss-120b:free)
OpenAI GPT-OSS 20B (openai/gpt-oss-20b:free)
MiniMax M2.5 (minimax/minimax-m2.5:free)

Judge (via OpenRouter free tier):

NVIDIA Nemotron 3 Super 120B (nvidia/nemotron-3-super-120b-a12b:free)

Why this configuration: All four models route through OpenRouter using a single API key and one OpenAI-compatible client via config/llm.py. Nemotron is architecturally independent from all three evaluators (NVIDIA vs OpenAI vs MiniMax) — eliminates same-family circularity. Earlier candidates (Gemma 4 31B, Qwen 3 30B) were dropped due to persistent upstream rate limiting on OpenRouter free tier.
Evaluation Dimensions
Four dimensions scored 0.00–1.00 with explicit anchor points to force score distribution:

Factuality: claim accuracy with 0.85/0.60/0.30 anchors. Returns null when prompt contains no verifiable claims.
Reasoning: inferential validity AND depth. Returns null when no multi-step reasoning required.
Instruction following: computed as constraints_met / constraints_total with partial credit. Scores implied intent when no explicit instructions exist — never null.
Format compliance: structural exactness against requested output format.

Judge system prompt compressed to ~180 tokens to stay within free-tier upstream capacity. Includes "most responses score 0.40–0.85" range mandate to prevent judge defaulting to 1.00 for everything competent.
Rate Limit Architecture — Sequential Daily Replenishment
OpenRouter free tier constraints: 50 RPD global across all models, 20 RPM global.
The math:

200 prompts × 3 evaluators = 600 evaluator calls
600 responses × 1 judge call = 600 judge calls
Total: 1,200 API calls
Each prompt fully scored = 6 calls (3 evaluator + 3 judge)
Daily capacity: 50 ÷ 6 = ~8 prompts/day
Completion time: ~24 days

Why this approach over multi-provider arbitrage: Cross-provider routing (Groq, Google AI Studio, NVIDIA direct, HuggingFace) was evaluated and rejected. Different providers serve different quantization levels and inference configurations for the "same" model — scores would conflate model quality with provider inference variance. Single-provider sequential execution is methodologically cleaner. Documenting this tradeoff honestly is itself a hiring signal.
Implementation:

config/llm.py: single OpenRouter client, API_CALL_DELAY=4.0s (stays under 20 RPM), per-provider lock, exponential backoff on 429s, DailyQuotaExhausted exception on "free-models-per-day" error
batch_eval.py: atomic parquet checkpointing after every single call via write → fsync → os.replace(). Crash, power loss, or quota exhaustion cannot lose data. On quota exhaustion: logs timestamp, writes schedule_next_run.bat for Windows Task Scheduler at UTC midnight reset, exits cleanly. Resume logic: reads existing parquet on startup, skips completed (prompt_id, model) pairs.
eval_state.json: tracks last completed prompt_id per model, atomically written after every call
failed_calls.json: logs permanently failed calls for retry at end of each day's run

Response Truncation
Evaluator responses truncated to 1,500 characters before sending to judge. Reduces judge input by 30–40%, preventing upstream throttling on free tier. Threshold preserves substantive content while eliminating padding and repetition.
Empty Judge Response Handling
If judge returns empty content (observed with some free-tier models under load): all four dimensions scored as float("nan"), flagged judge_empty: True, parse_error: "judge_returned_empty_response". Excluded from leaderboard calculations. No silent data corruption.
Prompt Suite
200 prompts across 5 categories (40 each). Includes an edge case handling category with deliberately ambiguous, underspecified, and contradictory prompts to force score divergence between evaluator models. Generated via generate_prompts.py.
System Prompts
Evaluator (identical across all 3 models — control variable):
Minimal and neutral. Instructs model to answer directly, follow format instructions, avoid disclaimers. Intentionally avoids biasing any model toward a particular response style.
Judge (Nemotron only):
Score-anchored rubric with explicit 0.85/0.60/0.30 reference points per dimension. Includes penalty for hedging, padding, repetition. Reward for precision and completeness. Concrete null usage examples. Compressed to ~180 tokens.
Frontend
React + Vite + TypeScript + Tailwind + Shadcn UI + Recharts. Built via Google AI Studio scaffold, then wired to data via Claude Code. Neo-brutalist design system with cream monochromatic aesthetic, Poppy (#D8560E) as primary accent. Dark mode toggle. Expandable chart overlays. Pages: Overview, Rankings, Dimensions, Frontier, Methods, Blog.
Hardcoded fallback data for three models with scores, costs, and latency values. Dashboard reads from public/data/leaderboard.csv and public/data/eval_results.csv via src/lib/loadCsv.ts.
Backend
No live backend. Python eval harness runs locally once, outputs CSVs. Dashboard is a static site on Vercel. No Modal, no Railway, no FastAPI.
Blog Post
Integrated into the dashboard as a page. Covers methodology, model selection reasoning, judge independence argument, evaluation dimensions with null edge cases, response truncation rationale, sequential daily replenishment architecture, and "what I'd do with internal eval infrastructure" hiring signal paragraph.
Deployment
Frontend only → Vercel. Static site consuming pre-computed CSVs.
Eval harness runs locally on Windows 11 via python batch_eval.py.
Single env var: OPENROUTER_API_KEY.
Key Modifications During Build

Judge model changed 3 times: Gemini 2.0 Flash (AI Studio rate limits) → Gemma 4 31B (upstream throttled) → Qwen 3 30B (upstream throttled + empty responses) → NVIDIA Nemotron 3 Super (stable)
Evaluator GPT-OSS 20B added: replaced Gemma 4 26B A4B to avoid same-family circularity with any potential Gemma judge
Multi-provider arbitrage rejected: evaluated 5-provider pool (Groq, Google, NVIDIA, Together, OpenRouter) — rejected for methodological contamination
Scoring rubric hardened: added explicit anchor points and range mandate after initial scores clustered at 0.90+ for all models
Prompt suite expanded: edge case category added with ambiguous, contradictory, and underspecified prompts to force model differentiation
Frontend pivoted from Streamlit to React + Vite: consistent with P2, P5, P7, P10 stack on Verc

perf: concurrent fan-out across (prompt, model) pairs
- global 20-RPM token bucket (set to 18 for 10% headroom) in config/llm.py;
  per-provider locks still serialize same-provider calls (e.g. all judge
  calls share nvidia/, all openai/* share openai/)
- raise DAILY_CALL_BUDGET 50 -> 950 now that paid-account :free RPD is 1000
- ThreadPoolExecutor with PROMPT_WORKERS=len(EVALUATOR_MODELS) processes
  (prompt, model) pairs concurrently; pending_eval becomes pending_evals
  dict keyed by pid|model so concurrent pairs do not collide on the
  mid-judge checkpoint
- state mutations behind _STATE_LOCK; DailyQuotaExhausted bubbles up via
  _QuotaSignal so the executor cancels in-flight work and schedules the
  next-day resume cleanly
- expected runtime drops from ~8 days to ~1-2 days (bound by 18 RPM)

O(n^2) parquet append, non-interactive runs, call-count, utcnow
- per-row parquet files in data/rows/ make append O(1) instead of O(n);
  consolidate to single eval_results.parquet on completion (and CSV)
- --yes flag and TTY detection so schtasks-launched runs no longer hang
  on input() — auto-resume now actually works
- count total_calls on each attempt (not just success) so the local
  mirror tracks OpenRouter's quota debit on failed retries
- replace deprecated datetime.utcnow() with datetime.now(timezone.utc)
- fix off-by-one in eval/judge retry log (was '5/3' on last attempt)

safety: enforce :free-only models, disable paid fallbacks, surface credits
- assert all evaluator/judge model IDs end in ':free' at import (fail-fast)
- pass provider.allow_fallbacks=false on every chat call so unavailable :free
  variants 4xx instead of silently routing to paid providers
- pre-flight GET /api/v1/key + record baseline usage in eval_state.json
- end-of-run credit display with spent-this-run delta and warning above $0.01