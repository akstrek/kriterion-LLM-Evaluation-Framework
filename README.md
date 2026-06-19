# Kriterion

*An auto-scored, reproducible LLM eval harness — built on free-tier infra, judged by an independent model.*

[![Live Dashboard](https://img.shields.io/badge/Live-Dashboard-0A0806?style=for-the-badge&logo=vercel&logoColor=white)](https://kriterion-eight.vercel.app/)
&nbsp;
[![Blog](https://img.shields.io/badge/Read-the_Blog-C8873A?style=for-the-badge)](https://kriterion-eight.vercel.app/blog)

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.8-3178C6?style=flat-square&logo=typescript&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-6-646CFF?style=flat-square&logo=vite&logoColor=white)
![Tailwind](https://img.shields.io/badge/Tailwind-4-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)
![Recharts](https://img.shields.io/badge/Recharts-3-22B5BF?style=flat-square)
![OpenRouter](https://img.shields.io/badge/OpenRouter-free_tier-6E57FF?style=flat-square)
![License](https://img.shields.io/badge/License-unspecified-lightgrey?style=flat-square)

**3 evaluator models · 1 judge · 600 prompts · 1,800 pairs · 5 scoring dimensions · 0 dollars spent**

---

## What This Is

Kriterion mirrors the kind of systematic, auto-scored evaluation work done by evals teams at frontier labs, reproduced end-to-end on free-tier infrastructure. It scores three open-weight evaluators (Moonshot Kimi K2.6, Google Gemma 4 31B IT, OpenAI GPT-OSS 120B) against 600 prompts across 6 categories, with NVIDIA Nemotron 3 Super 120B as an architecturally independent judge. That is 600 prompts × 3 evaluators = 1,800 evaluated pairs, each tagged easy / medium / hard / expert so model separation is visible at the top tier. Every score and chart is generated from real eval runs, not synthetic data. The most differentiating decision is in the runtime: a Hierarchical Token Bucket scheduler treats multi-provider rate limits as a bandwidth-shaping problem, so the entire pipeline self-paces through quota exhaustion without any OS-level scheduling, and a bounded patient multi-pass sweep drives the transient-429 tail to zero without manual re-runs.

Architecture deep dive → [Blog](https://kriterion-eight.vercel.app/blog) · Scoring methodology → [Methods](https://kriterion-eight.vercel.app/methods)

---

## Architecture at a Glance

### ⚡ Eval Pipeline (Backend)

```
prompts/prompt_suite.json   (600 prompts × 6 categories, difficulty-tagged)
            │
            ▼
       batch_eval.py ──── HTB Scheduler   root: 0.3 req/s · 950 RPD
            │                  │          ├── nvidia    300 RPD (judge)
            │             DRR Pair         ├── google   325 RPD
            │             Selector         ├── moonshot 163 RPD
            │                  │           └── openai   163 RPD
            │             Patient multi-pass sweep (transient-429 tail → 0)
            ▼                  ▼
       evaluator.py ◄──── config/llm.py    fallback routing per provider
       (3 workers)        adaptive throttle (halves rate on 429>30%)
            │
            ▼
       Judge scoring ──── nvidia/nemotron-3-super-120b-a12b:free
            │
            ▼
       data/rows/*.parquet   (atomic tmp → fsync → os.replace per row)
            │
            ▼
       leaderboard.py ──── bootstrap CI · two-score aggregation · difficulty CSV
            │
            ▼
       public/data/leaderboard.csv ──► React dashboard ──► Vercel
```

| Decision | What | Why |
|:---|:---|:---|
| HTB quota scheduling | Hierarchical Token Bucket (Devera, 2002) | Multi-tenant rate limits are a bandwidth-shaping problem. Providers get guaranteed shares plus idle-borrow. |
| DRR pair selection | Deficit Round Robin (Shreedhar & Varghese, 1996) | Uniform model coverage even under partial quota exhaustion. Leaderboard validity requires equal samples. |
| Atomic checkpointing | tmp → fsync → `os.replace` per row to `data/rows/*.parquet` | Crash-safe. Resume reads parquet rows, not state pointers. |
| Sleep-in-process | Blocks until 00:01 UTC reset, 5-min poll | No `schtasks`, no separate OS dependency. One self-pacing process. |
| Two-score aggregation | `overall_applicable` + `overall_strict` | Zero free parameters. Fully reproducible from parquet alone. |
| Fallback routing | Primary → fallback per provider, debits fallback's HTB leaf | Resilience without violating OpenRouter TOS or burning credits. |
| Adaptive throttle | Halve root rate to 0.15/s for 300s when trailing 429-rate > 30% | Backs off automatically when a provider degrades, restores on cooldown. |
| Retry-After-aware backoff | Honor server `Retry-After` / `X-RateLimit-Reset`, else full-jitter exponential; only 429 / 5xx / timeouts retried | Wastes no daily-quota units on un-retryable 4xx; spreads worker retries so they don't re-sync. |
| Patient multi-pass sweep | Bounded outer loop in `batch_eval.main`: re-run remaining pairs with widening gaps (5 / 15 / 30 min, 4 passes) | Transient upstream 429s need *time between attempts*, not just a retry; this drains the ~4% tail without manual re-runs. |

Full architecture story → [Blog](https://kriterion-eight.vercel.app/blog) · Infrastructure details → [Methods](https://kriterion-eight.vercel.app/methods)

---

### 🖥️ Dashboard (Frontend)

![React 19](https://img.shields.io/badge/React-19.0-61DAFB?style=flat&logo=react&logoColor=white)
![Vite 6](https://img.shields.io/badge/Vite-6.2-646CFF?style=flat&logo=vite&logoColor=white)
![TypeScript 5.8](https://img.shields.io/badge/TypeScript-5.8-3178C6?style=flat&logo=typescript&logoColor=white)
![Tailwind 4](https://img.shields.io/badge/Tailwind-4.1-06B6D4?style=flat&logo=tailwindcss&logoColor=white)
![Motion 12](https://img.shields.io/badge/Motion-12.23-FF0080?style=flat)
![Recharts 3](https://img.shields.io/badge/Recharts-3.8-22B5BF?style=flat)
![Router 7](https://img.shields.io/badge/React_Router-7.14-CA4245?style=flat&logo=reactrouter&logoColor=white)

Fixed `PageFrame` + interior `ScrollableZone` give a cinematic outer frame; `GrainOverlay` adds procedural SVG film grain; `AnimatePresence` crossfades between lazy-loaded routes (`/`, `/rankings`, `/dimensions`, `/methods`, `/blog`); data arrives as a static CSV parsed at runtime with Papa Parse — no API server.

![Kriterion Dashboard](./docs/screenshots/overview.png)

---

## 🤖 Models

All models are `:free`-enforced at import time. `allow_fallbacks: false` prevents silent routing to paid providers.

| Role | Primary | Fallback |
|:---:|:---|:---|
| Judge | `nvidia/nemotron-3-super-120b-a12b:free` | `nvidia/nemotron-3-nano-30b-a3b:free` |
| Evaluator | `moonshotai/kimi-k2.6:free` | `google/gemma-4-26b-a4b-it:free` |
| Evaluator | `google/gemma-4-31b-it:free` | `openai/gpt-oss-20b:free` |
| Evaluator | `openai/gpt-oss-120b:free` | `google/gemma-4-31b-it:free` |

Model selection rationale → [Blog](https://kriterion-eight.vercel.app/blog)

---

## 🎯 Scoring

| Dimension | Measures | In headline? | Null when |
|:---|:---|:---:|:---|
| Factuality | Claim accuracy against ground knowledge | ✓ | No factual claims in prompt |
| Reasoning | Inferential validity + depth | ✓ | No reasoning required |
| Instruction Following | Constraint satisfaction (met / total) | ✓ | Never null |
| Verbosity | Conciseness relative to task | ✓ | Never null |
| Format Compliance | Structural exactness vs. requested format | ✗ (reported only) | Never null |

Scored 0.00–1.00 by the judge using calibrated anchor points; most responses land in 0.40–0.85. The headline mean averages the four ✓ dimensions; `format_compliance` is scored on every response and reported as its own column, but excluded from the headline because structural pickiness is a separate axis from capability. Full rubric → [Methods](https://kriterion-eight.vercel.app/methods).

Aggregation: `overall_applicable` (per-row mean over non-null headline dims, then per-model mean) and `overall_strict` (per-row NaN-impute with model's own dim-mean, then mean). Bootstrap 95% CIs: 1,000 resamples, seed 42, pure numpy. A second CSV, `leaderboard_by_difficulty.csv`, reports the same headline per `(model × difficulty)` tier.

<details>
<summary>Judge system prompt (verbatim, from <code>config/llm.py</code>)</summary>

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

</details>

---

## 🔄 Reproduce the Eval

Windows 11 · PowerShell · Python 3.11 · Node.js LTS.

```powershell
git clone https://github.com/akstrek/kriterion-LLM-Evaluation-Framework.git
cd kriterion-LLM-Evaluation-Framework
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `.env` at the repo root with `OPENROUTER_API_KEY=your_key_here`, then:

```powershell
python generate_prompts.py                              # (1) skip if prompts/prompt_suite.json is committed
python batch_eval.py                                    # (2) ~4 days at free-tier 950 RPD
python leaderboard.py                                   # (3) aggregate to data/leaderboard.csv (+ leaderboard_by_difficulty.csv, auto-mirrored to public/data/)
npm install; npm run dev                                # (4) dashboard at localhost:3000
```

> ℹ️ **Step 2 spans several calendar days on free tier.** 3,600 logical API calls (1,800 evaluator + 1,800 judge) against a 950 RPD root budget. The runner sleeps in-process until 00:01 UTC when the daily quota exhausts, then a bounded patient multi-pass sweep re-runs any pairs still stuck on transient upstream 429s with widening gaps, so a single invocation drives the run to completion with no manual intervention after launch. `leaderboard.py` auto-publishes both CSVs into `public/data/`, so no manual copy step is needed.

---

## 🖼️ Dashboard Only (no eval run)

For reviewers who want to see the frontend with existing results:

```powershell
npm install
npm run dev
```

Loads `public/data/leaderboard.csv`. Falls back to a small embedded demo dataset if the CSV is missing.

---

## ⚠️ Known Limitations

- **Single judge model** — same-family scoring bias is possible (Zheng et al., 2023). No multi-judge ensemble yet.
- **No human-rater validation sample** — inter-rater reliability with the judge is unknown.
- **Response truncation** — evaluator responses are truncated to ~1,500 characters before judge scoring.
- **Free-tier variability** — provider availability and latency shift through the day; the adaptive throttle dampens but doesn't eliminate this.
- **Gemma 4 31B dual role** — serves as Evaluator 2 *and* as fallback for Evaluator 3, creating single-provider risk if Google's free tier degrades.

Full discussion → [Methods](https://kriterion-eight.vercel.app/methods).

---

## License

No license file specified in this repository.

---

<details>
<summary>Project structure</summary>

```
kriterion/
├── batch_eval.py            # Orchestrator: HTB + DRR + worker threads + quota sleep
├── evaluator.py             # run_model() + score_response() (judge call)
├── leaderboard.py           # Two-score aggregation + bootstrap CI
├── generate_prompts.py      # Prompt suite generator
├── config/
│   ├── llm.py               # Models, HTB tree, adaptive throttle, system prompts
│   └── scheduler.py         # DRR scheduler + quota-sleep loop
├── prompts/prompt_suite.json
├── data/
│   ├── rows/                # Per-row atomic parquet checkpoints
│   ├── eval_results.parquet
│   └── leaderboard.csv
├── public/data/leaderboard.csv   # Static CSV consumed by the dashboard
├── src/
│   ├── components/{charts,layout,pages}/
│   └── lib/loadCsv.ts
├── architecture.md
└── requirements.txt
```

</details>

<p align="center">Built by <a href="https://github.com/akstrek">akstrek</a> · <a href="https://kriterion-eight.vercel.app/">Live Dashboard</a> · <a href="https://kriterion-eight.vercel.app/blog">Blog</a></p>
