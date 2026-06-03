import Papa from 'papaparse';
import { ModelPerformance } from '../types';

const FALLBACK_DATA: ModelPerformance[] = [
  {
    rank: 1,
    model: "moonshotai/kimi-k2.6:free",
    overallScore: 0.9333,
    overallStrict: 0.9244,
    ciLow: 0.9141,
    ciHigh: 0.9518,
    factuality: 0.969,
    reasoning: 0.8559,
    instructionFollowing: 0.8925,
    formatCompliance: 0.98,
    costPerPrompt: 0,
    latencyP50Ms: 14066,
    latencyP95Ms: 137704,
    nPrompts: 200,
    nJudgeEmpty: 1,
    nFallback: 22,
    catFactualRecall: 0.9991,
    catMultiStepReasoning: 0.9683,
    catInstructionFollowing: 0.9302,
    catCodeGeneration: 0.9806,
    catAdversarialEdgeCases: 0.7853,
  },
  {
    rank: 2,
    model: "google/gemma-4-31b-it:free",
    overallScore: 0.9137,
    overallStrict: 0.9074,
    ciLow: 0.8909,
    ciHigh: 0.9342,
    factuality: 0.9506,
    reasoning: 0.8448,
    instructionFollowing: 0.8761,
    formatCompliance: 0.958,
    costPerPrompt: 0,
    latencyP50Ms: 4522,
    latencyP95Ms: 15353,
    nPrompts: 200,
    nJudgeEmpty: 0,
    nFallback: 86,
    catFactualRecall: 1.0,
    catMultiStepReasoning: 0.9542,
    catInstructionFollowing: 0.9209,
    catCodeGeneration: 0.9655,
    catAdversarialEdgeCases: 0.728,
  },
  {
    rank: 3,
    model: "openai/gpt-oss-120b:free",
    overallScore: 0.9082,
    overallStrict: 0.8989,
    ciLow: 0.8863,
    ciHigh: 0.931,
    factuality: 0.9541,
    reasoning: 0.8204,
    instructionFollowing: 0.8579,
    formatCompliance: 0.9631,
    costPerPrompt: 0,
    latencyP50Ms: 8292,
    latencyP95Ms: 32059,
    nPrompts: 199,
    nJudgeEmpty: 1,
    nFallback: 0,
    catFactualRecall: 1.0,
    catMultiStepReasoning: 0.9634,
    catInstructionFollowing: 0.9456,
    catCodeGeneration: 0.9242,
    catAdversarialEdgeCases: 0.7051,
  },
];

function num(v: any, fallback = 0): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function mapRow(row: any): ModelPerformance | null {
  if (!row || !row.model) return null;
  const overall = Number(row.overall_applicable);
  if (!Number.isFinite(overall)) return null;
  return {
    rank: num(row.rank),
    model: String(row.model),
    overallScore: overall,
    overallStrict: Number.isFinite(Number(row.overall_strict)) ? Number(row.overall_strict) : undefined,
    ciLow: Number.isFinite(Number(row.ci_low)) ? Number(row.ci_low) : undefined,
    ciHigh: Number.isFinite(Number(row.ci_high)) ? Number(row.ci_high) : undefined,
    factuality: num(row.avg_factuality),
    reasoning: num(row.avg_reasoning),
    instructionFollowing: num(row.avg_instruction_following),
    formatCompliance: num(row.avg_format_compliance),
    costPerPrompt: num(row.avg_cost_per_prompt_usd),
    latencyP50Ms: num(row.latency_p50_ms),
    latencyP95Ms: num(row.latency_p95_ms),
    nPrompts: num(row.n_prompts),
    nJudgeEmpty: num(row.n_judge_empty),
    nFallback: num(row.n_fallback),
    catFactualRecall: num(row.cat_factual_recall),
    catMultiStepReasoning: num(row.cat_multi_step_reasoning),
    catInstructionFollowing: num(row.cat_instruction_following),
    catCodeGeneration: num(row.cat_code_generation),
    catAdversarialEdgeCases: num(row.cat_adversarial_edge_cases),
  };
}

export async function loadLeaderboard(): Promise<ModelPerformance[]> {
  try {
    const res = await fetch('/data/leaderboard.csv');
    if (!res.ok) throw new Error('Not found');

    const contentType = res.headers.get('content-type');
    if (contentType && contentType.includes('text/html')) {
      throw new Error('Received HTML instead of CSV');
    }

    const text = await res.text();

    return new Promise((resolve) => {
      Papa.parse(text, {
        header: true,
        dynamicTyping: true,
        skipEmptyLines: true,
        complete: (results) => {
          const mapped = (results.data as any[])
            .map(mapRow)
            .filter((r): r is ModelPerformance => r !== null);
          resolve(mapped.length ? mapped : FALLBACK_DATA);
        },
        error: () => resolve(FALLBACK_DATA),
      });
    });
  } catch {
    return FALLBACK_DATA;
  }
}

export async function loadEvalResults() {
  return loadLeaderboard();
}

export async function loadDimensions() {
  return ["Factuality", "Reasoning", "Instruction Following", "Format Compliance"];
}
