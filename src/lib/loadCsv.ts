import Papa from 'papaparse';
import { ModelPerformance } from '../types';

const FALLBACK_DATA: ModelPerformance[] = [
  {
    model: "Claude Sonnet 4",
    overallScore: 0.92,
    factuality: 0.88,
    reasoning: 0.94,
    instructionFollowing: 0.95,
    formatCompliance: 0.98,
    costPerPrompt: 0.003,
    latencyP50: 1.2
  },
  {
    model: "GPT-4o",
    overallScore: 0.94,
    factuality: 0.91,
    reasoning: 0.95,
    instructionFollowing: 0.96,
    formatCompliance: 0.95,
    costPerPrompt: 0.005,
    latencyP50: 1.8
  },
  {
    model: "Gemini Flash 2.0",
    overallScore: 0.89,
    factuality: 0.85,
    reasoning: 0.90,
    instructionFollowing: 0.91,
    formatCompliance: 0.94,
    costPerPrompt: 0.001,
    latencyP50: 0.9
  }
];

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
         complete: (results) => {
           // Ensure it actually looks like our data
           const firstRow = results.data[0] as any;
           if (results.data && results.data.length > 0 && firstRow && typeof firstRow.overallScore === 'number') {
              // Ensure all required numeric fields exist to prevent toFixed() crashes
              const sanitizedData = results.data.map((row: any) => ({
                model: String(row.model || 'Unknown'),
                overallScore: Number(row.overallScore) || 0,
                factuality: Number(row.factuality) || 0,
                reasoning: Number(row.reasoning) || 0,
                instructionFollowing: Number(row.instructionFollowing) || 0,
                formatCompliance: Number(row.formatCompliance) || 0,
                costPerPrompt: Number(row.costPerPrompt) || 0,
                latencyP50: Number(row.latencyP50) || 0,
              })) as ModelPerformance[];
              resolve(sanitizedData);
           } else {
              resolve(FALLBACK_DATA);
           }
         },
         error: () => resolve(FALLBACK_DATA)
      });
    });
  } catch (e) {
    return FALLBACK_DATA;
  }
}

export async function loadEvalResults() {
  return loadLeaderboard();
}

export async function loadDimensions() {
  return ["Factuality", "Reasoning", "Instruction Following", "Format Compliance"];
}
