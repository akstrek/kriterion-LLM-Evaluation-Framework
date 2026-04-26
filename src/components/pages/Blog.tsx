import { motion } from "motion/react";
import { BottomLeft } from "../layout/BottomLeft";
import { BottomRight } from "../layout/BottomRight";
import { ScrollableZone } from "../layout/ScrollableZone";

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.45, ease: "easeOut", delay: i * 0.07 },
  }),
};

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] uppercase tracking-[0.2em] text-[#C8C2B8] mb-3 font-medium">
      {children}
    </p>
  );
}

function Divider() {
  return <div className="border-t border-white/[0.06] my-8" />;
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-block px-2 py-0.5 rounded-md bg-white/[0.06] border border-white/[0.08] text-[#C8C2B8] text-[11px] tracking-wide font-mono">
      {children}
    </span>
  );
}

export function Blog() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="absolute inset-0 z-10 pointer-events-none"
    >
      <BottomLeft title="Blog" />

      <ScrollableZone className="max-w-[760px] mx-auto">
        <div className="pointer-events-auto space-y-0 pb-8">

          {/* Header */}
          <motion.div custom={0} variants={fadeUp} initial="hidden" animate="show" className="mb-10">
            <SectionLabel>Design Architecture, April 2025</SectionLabel>
            <h2 className="font-display text-[#F5F0E8] text-[28px] md:text-[36px] font-black leading-tight tracking-[-0.03em] mb-4">
              How Kriterion Evaluates LLMs Without Trusting Any of Them
            </h2>
            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5">
              <p className="text-[#C8C2B8] text-[14px] leading-relaxed max-w-[580px]">
                A transparent walkthrough of the evaluation dimensions, prompt taxonomy, judge architecture, and reproducibility choices that make Kriterion's rankings defensible.
              </p>
            </div>
          </motion.div>

          {/* Section 1, Dimensions */}
          <motion.div custom={1} variants={fadeUp} initial="hidden" animate="show">
            <SectionLabel>01, Evaluation Dimensions</SectionLabel>
            <h3 className="font-display text-[#F5F0E8] text-[20px] font-bold tracking-tight mb-5">
              Four Dimensions, Zero Ambiguity
            </h3>
            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5 mb-6">
              <p className="text-[#C8C2B8] text-[13px] leading-relaxed">
                Every response is scored on exactly four continuous dimensions between 0 and 1. Each dimension has a precise definition, a deterministic or judge-based scoring rule, and a prompt that forces the judge to reason explicitly before returning a float.
              </p>
            </div>

            <div className="space-y-3">
              {[
                {
                  name: "Factual Accuracy",
                  tag: "factuality",
                  def: "Measures claim accuracy across the full 0–1 range. Null when the prompt contains no verifiable factual claims (creative writing, opinion prompts).",
                  rule: 'Nemotron: "List every factual claim. Mark each TRUE / FALSE / UNVERIFIABLE. Score = TRUE ÷ (TRUE + FALSE). Ignore UNVERIFIABLE." Returns float 0–1.',
                },
                {
                  name: "Reasoning Coherence",
                  tag: "reasoning",
                  def: "Scores both validity and depth of inferential steps. Null when the prompt requires no multi-step reasoning (simple recall, format tasks).",
                  rule: 'Nemotron: "Identify each inferential step. Mark each VALID / INVALID / REDUNDANT. Score = VALID ÷ (VALID + INVALID). Ignore REDUNDANT." Returns float 0–1.',
                },
                {
                  name: "Instruction Fidelity",
                  tag: "instruction_following",
                  def: "Counts explicit constraints met divided by total constraints. Awards partial credit per constraint. When no explicit instructions exist, scores against reasonable implied intent for that prompt type — never null.",
                  rule: 'Nemotron: "List every explicit instruction/constraint. Mark each SATISFIED / VIOLATED. Score = SATISFIED ÷ total constraints." Returns float 0–1.',
                },
                {
                  name: "Format Compliance",
                  tag: "format_compliance",
                  def: "Measures structural exactness against the requested output format. Penalises hedging, padding, and unnecessary preamble. Rewards precision.",
                  rule: "Deterministic parser first (JSON.parse, regex, code-fence detection). If unambiguous → score is final, Nemotron not called. If partial/ambiguous → Nemotron adjudicates edge cases.",
                },
              ].map((dim, i) => (
                <motion.div
                  key={dim.tag}
                  custom={2 + i}
                  variants={fadeUp}
                  initial="hidden"
                  animate="show"
                  className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] overflow-hidden"
                >
                  <div className="flex items-start gap-4 p-5">
                    <div className="flex-shrink-0 w-7 h-7 rounded-lg bg-white/[0.04] border border-white/[0.08] flex items-center justify-center mt-0.5">
                      <span className="text-[#C8C2B8] text-[10px] font-mono font-bold">{String(i + 1).padStart(2, "0")}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-2">
                        <span className="text-[#F5F0E8] text-[13px] font-semibold">{dim.name}</span>
                        <Pill>{dim.tag}</Pill>
                      </div>
                      <p className="text-[#C8C2B8] text-[12px] leading-relaxed mb-3">{dim.def}</p>
                      <div className="bg-white/[0.03] rounded-lg p-3 border border-white/[0.05]">
                        <p className="text-[10px] uppercase tracking-widest text-[#C8C2B8] mb-1.5 font-medium">Scoring Rule</p>
                        <p className="text-[#C8C2B8] text-[11px] leading-relaxed font-mono">{dim.rule}</p>
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>

          <Divider />

          {/* Section 2, Prompt Categories */}
          <motion.div custom={6} variants={fadeUp} initial="hidden" animate="show">
            <SectionLabel>02, Prompt Taxonomy</SectionLabel>
            <h3 className="font-display text-[#F5F0E8] text-[20px] font-bold tracking-tight mb-5">
              Five Categories, 40 Prompts Each
            </h3>
            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5 mb-6">
              <p className="text-[#C8C2B8] text-[13px] leading-relaxed">
                200 prompts total across 3 evaluated models yield 600 responses. Category selection was designed to stress different capability surfaces simultaneously, including adversarial cases where the correct behavior is restraint.
              </p>
            </div>

            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] overflow-hidden">
              <div className="px-5 pt-5 pb-2">
                <div className="grid grid-cols-[1fr_auto_auto] text-[10px] uppercase tracking-[0.15em] text-[#C8C2B8] pb-3 border-b border-white/[0.06]">
                  <span>Category</span>
                  <span className="text-right pr-8">Prompt Count</span>
                  <span className="text-right">What it stresses</span>
                </div>
              </div>
              <div className="px-5 pb-4 space-y-0">
                {[
                  { cat: "Factual Recall", n: 40, stress: "Accuracy, knowledge boundaries" },
                  { cat: "Multi-step Reasoning", n: 40, stress: "Logic chains, constraint satisfaction" },
                  { cat: "Instruction Following", n: 40, stress: "4+ simultaneous constraints" },
                  { cat: "Code Generation", n: 40, stress: "Spec adherence, edge cases, style" },
                  { cat: "Adversarial Edge Cases", n: 40, stress: "Hallucination, refusal, format collapse" },
                ].map((row, i) => (
                  <div
                    key={row.cat}
                    className={`grid grid-cols-[1fr_auto_auto] py-3 text-[13px] ${i < 4 ? "border-b border-white/[0.04]" : ""}`}
                  >
                    <span className="text-[#F5F0E8]">{row.cat}</span>
                    <span className="text-[#C8C2B8] font-mono text-[12px] text-right pr-8">{row.n}</span>
                    <span className="text-[#C8C2B8] text-[12px] text-right">{row.stress}</span>
                  </div>
                ))}
                <div className="grid grid-cols-[1fr_auto_auto] py-3 border-t border-white/[0.08] mt-1">
                  <span className="text-[#F5F0E8] text-[13px] font-semibold">Total</span>
                  <span className="text-[#F5F0E8] font-mono text-[13px] font-semibold text-right pr-8">200</span>
                  <span className="text-[#C8C2B8] text-[12px] text-right">× 3 models = 600 responses</span>
                </div>
              </div>
            </div>
          </motion.div>

          <Divider />

          {/* Section 3, Judge + System Prompt */}
          <motion.div custom={7} variants={fadeUp} initial="hidden" animate="show">
            <SectionLabel>03, Scoring Methodology</SectionLabel>
            <h3 className="font-display text-[#F5F0E8] text-[20px] font-bold tracking-tight mb-5">
              One External Judge, 1,200 API Calls
            </h3>
            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5 mb-5">
              <p className="text-[#C8C2B8] text-[13px] leading-relaxed">
                <span className="text-[#F5F0E8]">NVIDIA Nemotron 3 Super 120B</span> serves as the sole judge. 200 prompts × 3 evaluators = 600 evaluator calls producing 600 responses. Each response receives 1 judge call — 600 judge calls total, each producing a score dict across 4 dimensions. Total: 1,200 API calls. Total dimensions scored: 2,400.
              </p>
            </div>

            <p className="text-[10px] uppercase tracking-[0.2em] text-[#C8C2B8] mb-3 font-medium">
              Free models used via single provider OpenRouter
            </p>

            <div className="space-y-3 mb-6">
              {[
                {
                  name: "OpenAI GPT-OSS 120B",
                  meta: "Provider: OpenAI  |  Parameters: 120B",
                  release: "GPT-OSS 120B is OpenAI's latest open-weight model with knowledge cutoff through April 2024.",
                  highlight: "Trained on diverse instruction-following data, excelling at reasoning tasks and code generation with strong generalization across domains.",
                  link: "https://huggingface.co/openai/gpt-oss-120b",
                },
                {
                  name: "OpenAI GPT-OSS 20B",
                  meta: "Provider: OpenAI  |  Parameters: 20B",
                  release: "GPT-OSS 20B is OpenAI's lightweight open-weight variant with knowledge cutoff through April 2024.",
                  highlight: "Optimized for efficiency and speed while maintaining strong instruction-following and reasoning capabilities across diverse tasks.",
                  link: "https://huggingface.co/openai/gpt-oss-20b",
                },
                {
                  name: "MiniMax M2.5",
                  meta: "Provider: MiniMax  |  Parameters: 256B (MoE)",
                  release: "MiniMax M2.5 is MiniMax's latest mixture-of-experts model with knowledge cutoff through September 2024.",
                  highlight: "MoE architecture enables efficient routing to specialized expert subnetworks, achieving superior reasoning and multilingual performance with minimal latency.",
                  link: "https://huggingface.co/MiniMaxAI/MiniMax-M2.5",
                },
              ].map((model) => (
                <a
                  key={model.name}
                  href={model.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group relative block bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5 transition-transform duration-200 hover:scale-[1.02]"
                >
                  <div className="absolute top-3 right-3 w-6 h-6 rounded-full bg-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M2.5 7.5L7.5 2.5M7.5 2.5H3.5M7.5 2.5V6.5" stroke="#0A0806" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </div>
                  <p className="text-[#F5F0E8] text-[13px] font-semibold mb-1">{model.name}</p>
                  <p className="text-[#C8C2B8] text-[11px] font-mono mb-3">{model.meta}</p>
                  <p className="text-[#C8C2B8] text-[12px] leading-relaxed mb-2">{model.release}</p>
                  <p className="text-[#C8C2B8] text-[12px] leading-relaxed">
                    <span className="text-[#F5F0E8] text-[11px] uppercase tracking-wider font-medium">Architectural Highlight  </span>
                    {model.highlight}
                  </p>
                </a>
              ))}
            </div>

            <a
              href="https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8"
              target="_blank"
              rel="noopener noreferrer"
              className="group relative block bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5 mb-6 transition-transform duration-200 hover:scale-[1.02]"
            >
              <div className="absolute top-3 right-3 w-6 h-6 rounded-full bg-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M2.5 7.5L7.5 2.5M7.5 2.5H3.5M7.5 2.5V6.5" stroke="#0A0806" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-[#C8C2B8] mb-3 font-medium">Judge Model</p>
              <p className="text-[#F5F0E8] text-[13px] font-semibold mb-1">NVIDIA Nemotron 3 Super 120B</p>
              <p className="text-[#C8C2B8] text-[11px] font-mono mb-3">Provider: NVIDIA  |  Parameters: 120B</p>
              <p className="text-[#C8C2B8] text-[12px] leading-relaxed mb-2">Nemotron 3 Super is NVIDIA's latest open-weight model with knowledge cutoff through March 2024.</p>
              <p className="text-[#C8C2B8] text-[12px] leading-relaxed mb-4">
                <span className="text-[#F5F0E8] text-[11px] uppercase tracking-wider font-medium">Architectural Highlight  </span>
                Trained on curated instruction-following data using NVIDIA's synthetic data generation pipeline, delivering exceptional performance on reasoning, factuality, and instruction adherence across domains.
              </p>
              <div className="border-l-2 border-white/[0.15] pl-4">
                <p className="text-[#C8C2B8] text-[12px] leading-relaxed italic">
                  Nemotron 3 Super is used in production by OpenClaw, Kilo Code, Hermes Agent, and Claude Code, making it one of the most battle-tested free-tier judge models available.
                </p>
              </div>
            </a>

            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5 mb-6">
              <p className="text-[#C8C2B8] text-[13px] leading-relaxed">
                Since all 3 evaluators are open-weight models accessed via a single provider, using any of them as judge introduces circularity. The judge must be architecturally independent from every model being evaluated.
              </p>
            </div>

            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] overflow-hidden mb-4">
              <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]">
                <span className="text-[10px] uppercase tracking-[0.15em] text-[#C8C2B8]">Evaluator System Prompt</span>
                <span className="text-[10px] text-[#C8C2B8] font-mono">applied to all 3 models</span>
              </div>
              <pre className="px-5 py-4 text-[11px] text-[#C8C2B8] font-mono leading-relaxed whitespace-pre-wrap overflow-x-auto">
{`You are a helpful, precise AI assistant. Answer the user's prompt directly.
Be concise. Be accurate. Follow all formatting instructions exactly.
If the prompt asks for a specific format (JSON, list, code), use that format only.
Do not add disclaimers, caveats, or meta-commentary about your response.`}
              </pre>
            </div>

            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] overflow-hidden mb-4">
              <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]">
                <span className="text-[10px] uppercase tracking-[0.15em] text-[#C8C2B8]">Judge System Prompt</span>
                <span className="text-[10px] text-[#C8C2B8] font-mono">JSON output only</span>
              </div>
              <pre className="px-5 py-4 text-[11px] text-[#C8C2B8] font-mono leading-relaxed whitespace-pre-wrap overflow-x-auto">
{`Score this prompt-response pair. Use full 0.00-1.00 range — most responses
score 0.40-0.85, not 1.00.

factuality: claim accuracy. 1.00=every claim verifiable. 0.85=minor imprecision.
0.60=one wrong claim. 0.30=multiple errors. 0.00=fabricated. null if no factual claims.

reasoning: inferential validity AND depth. 1.00=correct and insightful.
0.85=correct but shallow. 0.60=mostly correct, one weak step. 0.30=flawed logic.
0.00=incoherent. null if no reasoning required.

instruction_following: constraint satisfaction. Count explicit constraints
(length, format, scope, exclusions). Score = constraints_met / constraints_total.
Partial credit per constraint. Score implied intent if none explicit.

format_compliance: structural exactness. 1.00=perfect structure.
0.85=correct structure, minor deviation. 0.60=right format, wrong details.
0.30=wrong format. 0.00=no structure attempted.

Penalize: hedging, padding, unnecessary preamble, repetition.
Reward: precision, completeness within minimal tokens.

Return JSON only:
{"factuality":0.00,"reasoning":0.00,"instruction_following":0.00,"format_compliance":0.00}
null example: {"factuality":null,"reasoning":null,"instruction_following":0.85,"format_compliance":0.92}`}
              </pre>
            </div>

            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5">
              <p className="text-[#C8C2B8] text-[12px] leading-relaxed mb-4">
                For format compliance, the deterministic parser runs first. If the parse result is unambiguous, valid JSON, valid markdown structure, or clear structural failure, that score is final and Nemotron is not called. Nemotron adjudicates only edge cases where partial compliance makes a binary pass/fail incorrect. Every judge call logs the full reasoning field alongside the score; judge call cost and latency are tracked per dimension.
              </p>
              <p className="text-[#C8C2B8] text-[12px] leading-relaxed">
                Evaluator responses are truncated to 1,500 characters (cap at ~375 tokens) before being sent to the judge. This reduces judge input size by 30 to 40 percent, keeping calls within free-tier upstream capacity limits and preventing upstream throttling. The truncation threshold was chosen to preserve the substantive content of any response while eliminating padding and repetition.
              </p>
            </div>
          </motion.div>

          <Divider />

          {/* Section 4, Eval Infrastructure */}
          <motion.div custom={8} variants={fadeUp} initial="hidden" animate="show">
            <SectionLabel>04, Eval Infrastructure</SectionLabel>
            <h3 className="font-display text-[#F5F0E8] text-[20px] font-bold tracking-tight mb-5">
              Atomic Writes, Scheduled Resumption
            </h3>
            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5">
              <p className="text-[#C8C2B8] text-[13px] leading-relaxed">
                Kriterion runs on a resilient pipeline built for multi-day execution. Every call result is written atomically to parquet before the next call begins, so a crash, power loss, or daily quota exhaustion cannot cause data loss. On quota exhaustion, the runner schedules its own resumption via Windows Task Scheduler at UTC midnight reset and exits cleanly. The full 1,200-call evaluation completes over multiple days on a single provider's free tier, which is methodologically cleaner than cross-provider arbitrage, eliminating inference variance as a confounding variable. Total cost: $0.
              </p>
            </div>
          </motion.div>

          <Divider />

          {/* Section 5, Leaderboard Columns */}
          <motion.div custom={8} variants={fadeUp} initial="hidden" animate="show">
            <SectionLabel>05, Leaderboard Schema</SectionLabel>
            <h3 className="font-display text-[#F5F0E8] text-[20px] font-bold tracking-tight mb-5">
              What Gets Reported Per Model
            </h3>

            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {[
                  { col: "Overall Score", desc: "Avg across 4 dims" },
                  { col: "Factual Accuracy", desc: "Dimension score" },
                  { col: "Reasoning Coherence", desc: "Dimension score" },
                  { col: "Instruction Fidelity", desc: "Dimension score" },
                  { col: "Format Compliance", desc: "Dimension score" },
                  { col: "Avg Latency p50", desc: "Milliseconds" },
                  { col: "Avg Latency p95", desc: "Milliseconds" },
                  { col: "Avg Tokens Used", desc: "Per prompt" },
                  { col: "Cost per Prompt", desc: "USD" },
                  { col: "Score per Dollar", desc: "Efficiency index" },
                  { col: "Category Breakdown", desc: "5 sub-columns, per category avg" },
                ].map((item) => (
                  <div key={item.col} className="bg-white/[0.03] rounded-lg p-3 border border-white/[0.04]">
                    <p className="text-[#F5F0E8] text-[12px] font-medium mb-0.5">{item.col}</p>
                    <p className="text-[#C8C2B8] text-[11px]">{item.desc}</p>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>

          <Divider />

          {/* Section 6, Defensibility */}
          <motion.div custom={9} variants={fadeUp} initial="hidden" animate="show">
            <SectionLabel>06, What Makes This Defensible</SectionLabel>
            <h3 className="font-display text-[#F5F0E8] text-[20px] font-bold tracking-tight mb-5">
              Three Properties That Separate a Benchmark from a Blog Post
            </h3>

            <div className="space-y-4">
              {[
                {
                  n: "01",
                  title: "External Judge",
                  body: "The evaluation model shares no architecture, provider, or training data lineage with any evaluated model. This eliminates the self-preferencing bias documented in Zheng et al. (2023), where models systematically rate their own outputs higher. Publishing the judge model identity and every reasoning trace makes the bias profile auditable rather than hidden.",
                },
                {
                  n: "02",
                  title: "Deterministic Where Possible",
                  body: "Format compliance uses regex and parser checks as the primary scorer, invoking the LLM judge only for genuinely ambiguous edge cases. This means the highest-volume dimension, structural correctness, is reproducible without re-running the judge, and results are stable across repeated evaluations.",
                },
                {
                  n: "03",
                  title: "Full Prompt Suite Published",
                  body: "All 200 prompts, expected output types, and ground truth labels ship with the repo. Any researcher can rerun the harness against different models, swap the judge, or add dimensions without reverse-engineering the evaluation design. Reproducibility is the difference between a benchmark and a blog post.",
                },
              ].map((item) => (
                <div
                  key={item.n}
                  className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5 flex gap-5"
                >
                  <div className="flex-shrink-0">
                    <span className="font-display text-[32px] font-black text-white/[0.06] leading-none">{item.n}</span>
                  </div>
                  <div>
                    <p className="text-[#F5F0E8] text-[14px] font-semibold mb-2">{item.title}</p>
                    <p className="text-[#C8C2B8] text-[12px] leading-relaxed">{item.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>

          <Divider />

          {/* Section 7, Why External Judge */}
          <motion.div custom={10} variants={fadeUp} initial="hidden" animate="show">
            <SectionLabel>07, Why External Judge</SectionLabel>
            <h3 className="font-display text-[#F5F0E8] text-[20px] font-bold tracking-tight mb-5">
              Self-Evaluation Measures Self-Similarity, Not Quality
            </h3>
            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-6">
              <div className="border-l-2 border-white/[0.15] pl-5 mb-5">
                <p className="text-[#F5F0E8] text-[14px] leading-relaxed italic">
                  "A model evaluating its own outputs, or outputs from models in its family, systematically inflates scores due to shared stylistic priors and training distribution overlap. Any evaluation where the judge is also a contestant produces rankings that measure self-similarity rather than quality."
                </p>
              </div>
              <p className="text-[#C8C2B8] text-[13px] leading-relaxed">
                Nemotron 3 Super was selected because it is external to the evaluated set on all three axes that matter: provider (NVIDIA vs. OpenAI vs. MiniMax), architecture (dense decoder vs. dense decoder vs. MoE), and training data (no known overlap with GPT-OSS or MiniMax M2.5 fine-tuning corpora). The judge's reasoning traces are logged in full for every call, so the bias profile is auditable, not assumed away.
              </p>
            </div>
          </motion.div>

          {/* Footer */}
          <div className="pt-6 pb-2 text-center">
            <p className="font-sans font-bold text-[#F5F0E8] text-[12px] tracking-wide leading-relaxed">
              © Kriterion Portfolio | Evaluation underway.<br />Results will be published upon completion.
            </p>
          </div>
        </div>
      </ScrollableZone>

      <div className="pointer-events-auto">
        <BottomRight text="Design architecture for the Kriterion evaluation harness." />
      </div>
    </motion.div>
  );
}
