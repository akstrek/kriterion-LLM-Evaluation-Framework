export interface ModelPerformance {
  model: string;
  overallScore: number;
  overallStrict?: number;
  ciLow?: number;
  ciHigh?: number;
  factuality: number;
  reasoning: number;
  instructionFollowing: number;
  formatCompliance: number;
  costPerPrompt: number;
  latencyP50: number;
}
