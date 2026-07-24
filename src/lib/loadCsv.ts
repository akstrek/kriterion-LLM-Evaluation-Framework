import Papa from 'papaparse';
import { ModelPerformance, ModelDifficultyRow, JudgeCalibrationRow, JudgeAgreementRow } from '../types';

// FALLBACK_DATA is only used when the runtime CSV is missing or malformed —
// e.g. local dev before the first eval run. Values are placeholders, not
// claims about model performance under the new 5-dim rubric.
const FALLBACK_DATA: ModelPerformance[] = [
  {
    rank: 1,
    model: "moonshotai/kimi-k2.6:free",
    overallScore: 0.74,
    overallStrict: 0.73,
    ciLow: 0.72,
    ciHigh: 0.76,
    factuality: 0.78,
    reasoning: 0.71,
    instructionFollowing: 0.75,
    formatCompliance: 0.80,
    verbosity: 0.72,
    costPerPrompt: 0,
    latencyP50Ms: 14000,
    latencyP95Ms: 138000,
    nPrompts: 600,
    nJudgeEmpty: 1,
    nFallback: 22,
    catFactualRecall: 0.80,
    catMultiStepReasoning: 0.74,
    catInstructionFollowing: 0.76,
    catCodeGeneration: 0.71,
    catSafetyCalibration: 0.72,
    catHallucinationUnderUncertainty: 0.68,
  },
  {
    rank: 2,
    model: "google/gemma-4-31b-it:free",
    overallScore: 0.72,
    overallStrict: 0.71,
    ciLow: 0.70,
    ciHigh: 0.74,
    factuality: 0.76,
    reasoning: 0.70,
    instructionFollowing: 0.73,
    formatCompliance: 0.77,
    verbosity: 0.70,
    costPerPrompt: 0,
    latencyP50Ms: 4500,
    latencyP95Ms: 15000,
    nPrompts: 600,
    nJudgeEmpty: 0,
    nFallback: 86,
    catFactualRecall: 0.78,
    catMultiStepReasoning: 0.72,
    catInstructionFollowing: 0.74,
    catCodeGeneration: 0.69,
    catSafetyCalibration: 0.70,
    catHallucinationUnderUncertainty: 0.66,
  },
  {
    rank: 3,
    model: "openai/gpt-oss-120b:free",
    overallScore: 0.71,
    overallStrict: 0.70,
    ciLow: 0.69,
    ciHigh: 0.73,
    factuality: 0.75,
    reasoning: 0.69,
    instructionFollowing: 0.72,
    formatCompliance: 0.76,
    verbosity: 0.68,
    costPerPrompt: 0,
    latencyP50Ms: 8300,
    latencyP95Ms: 32000,
    nPrompts: 600,
    nJudgeEmpty: 1,
    nFallback: 0,
    catFactualRecall: 0.77,
    catMultiStepReasoning: 0.74,
    catInstructionFollowing: 0.73,
    catCodeGeneration: 0.70,
    catSafetyCalibration: 0.69,
    catHallucinationUnderUncertainty: 0.64,
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
    verbosity: num(row.avg_verbosity),
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
    catSafetyCalibration: num(row.cat_safety_calibration),
    catHallucinationUnderUncertainty: num(row.cat_hallucination_under_uncertainty),
  };
}

function mapCalibrationRow(row: any): JudgeCalibrationRow | null {
  if (!row || !row.dim) return null;
  const bandHitRate = Number(row.band_hit_rate);
  if (!Number.isFinite(bandHitRate)) return null;
  return {
    dim: String(row.dim),
    nProbes: num(row.n_probes),
    nRuns: num(row.n_runs),
    bandHitRate,
    mae: num(row.mae_vs_band_midpoint),
    testRetestStd: num(row.test_retest_std),
    nParseFailures: num(row.n_parse_failures),
  };
}

function mapAgreementRow(row: any): JudgeAgreementRow | null {
  if (!row || !row.dim) return null;
  const n = Number(row.n);
  if (!Number.isFinite(n)) return null;
  const pearsonR = Number(row.pearson_r);
  return {
    dim: String(row.dim),
    n,
    pearsonR: Number.isFinite(pearsonR) ? pearsonR : undefined,
    mae: num(row.mae),
    pctWithinOneStep: num(row.pct_within_one_step),
    nJudge1NanJudge2Val: num(row.n_judge1_nan_judge2_val),
    nJudge2NanJudge1Val: num(row.n_judge2_nan_judge1_val),
    nFallbackScored: num(row.n_fallback_scored),
  };
}

function mapDifficultyRow(row: any): ModelDifficultyRow | null {
  if (!row || !row.model || !row.difficulty) return null;
  const overall = Number(row.overall_applicable);
  if (!Number.isFinite(overall)) return null;
  const tier = String(row.difficulty);
  if (!["easy", "medium", "hard", "expert"].includes(tier)) return null;
  return {
    model: String(row.model),
    difficulty: tier as ModelDifficultyRow["difficulty"],
    overallScore: overall,
    factuality: num(row.avg_factuality),
    reasoning: num(row.avg_reasoning),
    instructionFollowing: num(row.avg_instruction_following),
    formatCompliance: num(row.avg_format_compliance),
    verbosity: num(row.avg_verbosity),
    nPrompts: num(row.n_prompts),
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

export async function loadLeaderboardByDifficulty(): Promise<ModelDifficultyRow[]> {
  try {
    const res = await fetch('/data/leaderboard_by_difficulty.csv');
    if (!res.ok) return [];

    const contentType = res.headers.get('content-type');
    if (contentType && contentType.includes('text/html')) return [];

    const text = await res.text();
    return new Promise((resolve) => {
      Papa.parse(text, {
        header: true,
        dynamicTyping: true,
        skipEmptyLines: true,
        complete: (results) => {
          const mapped = (results.data as any[])
            .map(mapDifficultyRow)
            .filter((r): r is ModelDifficultyRow => r !== null);
          resolve(mapped);
        },
        error: () => resolve([]),
      });
    });
  } catch {
    return [];
  }
}

export async function loadJudgeCalibration(): Promise<JudgeCalibrationRow[]> {
  try {
    const res = await fetch('/data/judge_calibration.csv');
    if (!res.ok) return [];

    const contentType = res.headers.get('content-type');
    if (contentType && contentType.includes('text/html')) return [];

    const text = await res.text();
    return new Promise((resolve) => {
      Papa.parse(text, {
        header: true,
        dynamicTyping: true,
        skipEmptyLines: true,
        complete: (results) => {
          const mapped = (results.data as any[])
            .map(mapCalibrationRow)
            .filter((r): r is JudgeCalibrationRow => r !== null);
          resolve(mapped);
        },
        error: () => resolve([]),
      });
    });
  } catch {
    return [];
  }
}

export async function loadJudgeAgreement(): Promise<JudgeAgreementRow[]> {
  try {
    const res = await fetch('/data/judge_agreement.csv');
    if (!res.ok) return [];

    const contentType = res.headers.get('content-type');
    if (contentType && contentType.includes('text/html')) return [];

    const text = await res.text();
    return new Promise((resolve) => {
      Papa.parse(text, {
        header: true,
        dynamicTyping: true,
        skipEmptyLines: true,
        complete: (results) => {
          const mapped = (results.data as any[])
            .map(mapAgreementRow)
            .filter((r): r is JudgeAgreementRow => r !== null);
          resolve(mapped);
        },
        error: () => resolve([]),
      });
    });
  } catch {
    return [];
  }
}

export async function loadEvalResults() {
  return loadLeaderboard();
}

export async function loadDimensions() {
  return ["Factuality", "Reasoning", "Instruction Following", "Format Compliance", "Verbosity"];
}
