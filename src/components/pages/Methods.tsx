import { motion } from "motion/react";
import { BottomLeft } from "../layout/BottomLeft";
import { BottomRight } from "../layout/BottomRight";
import { ScrollableZone } from "../layout/ScrollableZone";
import { ExpandableViz } from "../layout/ExpandableViz";
import promptSuite from "../../../prompts/prompt_suite.json";

// Mirror of config/llm.py — keep in sync.
const JUDGE_MODEL = "nvidia/nemotron-3-super-120b-a12b:free";

const JUDGE_SYSTEM_PROMPT = `Score this prompt-response pair. Use full 0.00-1.00 range — most responses score 0.40-0.85, not 1.00.
factuality: claim accuracy. 1.00=every claim verifiable. 0.85=minor imprecision. 0.60=one wrong claim. 0.30=multiple errors. 0.00=fabricated. null if no factual claims.
reasoning: inferential validity AND depth. 1.00=correct + insightful. 0.85=correct but shallow. 0.60=mostly correct, one weak step. 0.30=flawed logic. 0.00=incoherent. null if no reasoning required.
instruction_following: constraint satisfaction. Count explicit constraints (length, format, scope, exclusions). Score = constraints_met / constraints_total. Partial credit per constraint. Score implied intent if none explicit.
format_compliance: structural exactness. 1.00=perfect structure. 0.85=correct structure, minor deviation. 0.60=right format, wrong details. 0.30=wrong format. 0.00=no structure attempted.
Penalize: hedging, padding, unnecessary preamble, repetition. Reward: precision, completeness within minimal tokens.
Return JSON only: {"factuality":0.00,"reasoning":0.00,"instruction_following":0.00,"format_compliance":0.00}
null example: {"factuality":null,"reasoning":null,"instruction_following":0.85,"format_compliance":0.92}`;

const stripFree = (m: string) => m.replace(":free", "");
const titleCase = (s: string) =>
  s.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");

type PromptRow = { category: string };
const categoryOrder: string[] = [];
const categoryCounts: Record<string, number> = {};
for (const p of promptSuite as PromptRow[]) {
  if (!(p.category in categoryCounts)) {
    categoryOrder.push(p.category);
    categoryCounts[p.category] = 0;
  }
  categoryCounts[p.category] += 1;
}
const totalPrompts = Object.values(categoryCounts).reduce((a, b) => a + b, 0);

const scoreRubric: [string, string][] = [
  ["1.00", "Perfect"],
  ["0.85", "Minor imprecision"],
  ["0.60", "One clear error"],
  ["0.30", "Multiple failures"],
  ["0.00", "Fabricated / incoherent"],
  ["null", "Dimension not applicable"],
];

// Source: config/llm.py (_ROOT_RATE=0.3 → 18 RPM, _ROOT_RPD=950, _EVAL_RPD=650, _JUDGE_RPD=300).
const htbTree = `Root: 18 RPM, 950 RPD
├── nvidia/*    judge budget: 300 RPD
├── openai/*    eval budget (shared)
├── moonshot/*  eval budget (shared)
└── google/*    eval budget (shared)
Total eval: 650 RPD`;

const cardClass =
  "bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-5 sm:p-6 md:p-8 border border-white/[0.06] shadow-2xl";
const headingClass = "text-[#F5F0E8] font-display text-[16px] mb-4";
const bodyClass = "text-[#C8C2B8] text-[12px] leading-relaxed";
const labelClass =
  "text-[#F5F0E8] text-[11px] uppercase tracking-wider mb-1";

export function Methods() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="absolute inset-0 z-10 pointer-events-none"
    >
      <BottomLeft title="Methods" />

      <ScrollableZone>
        <ExpandableViz>
          <div className="w-full pointer-events-auto">
            <div className="mb-6">
              <h2 className="text-[#F5F0E8] font-display text-[22px] mb-2">
                Why You Should Believe This
              </h2>
              <p className="text-[#C8C2B8] text-[13px]">
                Every number on this site is produced by the pipeline below. This page shows exactly how.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

              {/* Section 1 — Scoring Rubric */}
              <div className={`${cardClass} md:col-span-2`}>
                <h3 className={headingClass}>Scoring Rubric</h3>
                <p className={`${bodyClass} mb-3`}>
                  Every response is scored by{" "}
                  <span className="text-[#F5F0E8] font-mono text-[12px]">
                    {stripFree(JUDGE_MODEL)}
                  </span>{" "}
                  using this exact prompt.
                </p>
                <pre className="bg-black/40 border border-white/10 rounded-lg p-4 text-[11px] text-[#C8C2B8] whitespace-pre-wrap font-mono leading-snug overflow-x-auto mb-4">
                  {JUDGE_SYSTEM_PROMPT}
                </pre>

                <div className="mb-3">
                  <div className="grid grid-cols-[80px_1fr] gap-x-4 gap-y-1">
                    <div className={`${labelClass} mb-0`}>Score</div>
                    <div className={`${labelClass} mb-0`}>Meaning</div>
                    {scoreRubric.map(([score, meaning]) => (
                      <div key={score} className="contents">
                        <div className="text-[#F5F0E8] text-[12px] font-mono border-t border-white/10 pt-1">
                          {score}
                        </div>
                        <div className="text-[#C8C2B8] text-[12px] border-t border-white/10 pt-1">
                          {meaning}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <p className={`${bodyClass} mb-2`}>
                  <span className="text-[#F5F0E8]">Range mandate:</span> most responses score 0.40–0.85.
                  The judge is instructed to use the full range, not cluster at 1.0.
                </p>
                <p className={bodyClass}>
                  Response text is truncated to 1,500 characters and prompt text to 500 characters before
                  judge scoring. Long-form generation quality beyond these limits is not measured.
                </p>
              </div>

              {/* Section 2 — Infrastructure */}
              <div className={cardClass}>
                <h3 className={headingClass}>Infrastructure</h3>
                <p className={`${bodyClass} mb-3`}>
                  This eval runs on OpenRouter's free tier — 20 RPM, 1,000 requests/day, hard ceiling,
                  no paid fallback. The scheduling infrastructure borrows from network traffic engineering.
                </p>
                <pre className="bg-black/40 border border-white/10 rounded-lg p-4 text-[11px] text-[#C8C2B8] font-mono leading-snug overflow-x-auto mb-4 whitespace-pre">
                  {htbTree}
                </pre>
                <ul className="space-y-1 mb-3">
                  <li className={bodyClass}>• Total prompts: {totalPrompts} × 3 evaluators = {totalPrompts * 3} pairs</li>
                  <li className={bodyClass}>• Total API calls: ~{(totalPrompts * 3 * 2).toLocaleString()} logical (eval + judge per pair)</li>
                  <li className={bodyClass}>• Daily budget: 950 calls/day (5% headroom under 1,000 RPD ceiling)</li>
                  <li className={bodyClass}>• Estimated run: 2 calendar days</li>
                </ul>
                <p className={bodyClass}>
                  Deficit Round Robin ensures uniform completion counts across evaluator models. The runner
                  sleeps in-process until quota resets — no OS-level scheduling dependencies.
                </p>
              </div>

              {/* Section 3 — Statistical Validity */}
              <div className={cardClass}>
                <h3 className={headingClass}>Statistical Validity</h3>
                <div className="space-y-4">
                  <div>
                    <p className={labelClass}>Bootstrap 95% CI</p>
                    <p className={bodyClass}>
                      Each model's overall score includes a 95% confidence interval from 1,000 bootstrap
                      resamples of per-prompt scores. The CI width reflects how stable the ranking is —
                      narrow intervals mean the ordering is robust, wide intervals mean more data would help.
                    </p>
                  </div>
                  <div>
                    <p className={labelClass}>Two Aggregations</p>
                    <p className={bodyClass}>
                      <span className="font-mono text-[#F5F0E8]">overall_applicable</span>: mean of scored
                      dimensions only (NaN dimensions excluded).{" "}
                      <span className="font-mono text-[#F5F0E8]">overall_strict</span>: NaN dimensions
                      imputed with the model's own mean for that dimension, then averaged. Both are
                      published. Neither has free parameters.
                    </p>
                  </div>
                  <div>
                    <p className={labelClass}>Judge Calibration</p>
                    <p className={bodyClass}>
                      Calibration probes (anchor responses with known scores run through the judge daily)
                      are planned but not yet implemented. This is standard practice in HELM and
                      lm-eval-harness. Until implemented, judge drift across multi-day runs is unmonitored.
                    </p>
                  </div>
                </div>
              </div>

              {/* Section 4 — Known Limitations */}
              <div className={cardClass}>
                <h3 className={headingClass}>Known Limitations</h3>
                <ul className="list-disc pl-4 space-y-2 text-[#C8C2B8] text-[12px] marker:text-[#F5F0E8] leading-relaxed">
                  <li>
                    <span className="text-[#F5F0E8]">Single judge model.</span> Nemotron-as-judge may
                    exhibit same-family scoring bias (Zheng et al. 2023). A second judge model with
                    inter-judge agreement reporting would strengthen validity.
                  </li>
                  <li>
                    <span className="text-[#F5F0E8]">No human validation.</span> Inter-rater reliability
                    between judge scores and human annotations is unknown. A 50-response hand-scored
                    sample with Spearman ρ is the standard mitigation — not yet done.
                  </li>
                  <li>
                    <span className="text-[#F5F0E8]">Truncation.</span> Responses capped at 1,500 chars
                    before judge scoring. Models that front-load quality in the first 1,500 chars are
                    systematically advantaged over models that build to a conclusion.
                  </li>
                  <li>
                    <span className="text-[#F5F0E8]">Free-tier availability.</span> Model availability on
                    OpenRouter :free varies by time of day. Eval results reflect whatever inference
                    capacity was available during the run window, not controlled conditions.
                  </li>
                  <li>
                    <span className="text-[#F5F0E8]">Gemma 4 31B dual role.</span>{" "}
                    <span className="font-mono">google/gemma-4-31b-it</span> serves as both Evaluator 2
                    and fallback for Evaluator 3. If Google's provider is unavailable, both roles are
                    affected simultaneously.
                  </li>
                </ul>
              </div>

              {/* Section 5 — Prompt Categories */}
              <div className={cardClass}>
                <h3 className={headingClass}>Prompt Categories</h3>
                <div className="space-y-2">
                  {categoryOrder.map((cat) => (
                    <div
                      key={cat}
                      className="flex justify-between border-b border-white/10 pb-1"
                    >
                      <span className="text-[#F5F0E8] text-[13px]">{titleCase(cat)}</span>
                      <span className="text-[#C8C2B8] text-[13px]">{categoryCounts[cat]}</span>
                    </div>
                  ))}
                  <div className="flex justify-between pt-1">
                    <span className="text-[#F5F0E8] text-[13px] font-bold">Total</span>
                    <span className="text-[#C8C2B8] text-[13px] font-bold">{totalPrompts}</span>
                  </div>
                </div>
              </div>

            </div>
          </div>
        </ExpandableViz>
      </ScrollableZone>

      <div className="pointer-events-auto">
        <BottomRight text="The pipeline behind every number — judge prompt, scheduler, stats, limits." />
      </div>
    </motion.div>
  );
}
