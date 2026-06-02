import Papa from 'papaparse';
import { ModelPerformance } from '../types';

const FALLBACK_DATA: ModelPerformance[] = [
  {
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
    latencyP50: 14.066,
  },
  {
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
    latencyP50: 4.522,
  },
  {
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
    latencyP50: 8.292,
  },
];

function mapRow(row: any): ModelPerformance | null {
  if (!row || !row.model) return null;
  const overall = Number(row.overall_applicable);
  if (!Number.isFinite(overall)) return null;
  return {
    model: String(row.model),
    overallScore: overall,
    overallStrict: Number(row.overall_strict) || undefined,
    ciLow: Number(row.ci_low) || undefined,
    ciHigh: Number(row.ci_high) || undefined,
    factuality: Number(row.avg_factuality) || 0,
    reasoning: Number(row.avg_reasoning) || 0,
    instructionFollowing: Number(row.avg_instruction_following) || 0,
    formatCompliance: Number(row.avg_format_compliance) || 0,
    costPerPrompt: Number(row.avg_cost_per_prompt_usd) || 0,
    latencyP50: (Number(row.latency_p50_ms) || 0) / 1000,
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
