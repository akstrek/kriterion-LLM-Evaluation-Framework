export interface ModelPerformance {
  rank: number;
  model: string;
  overallScore: number;
  overallStrict?: number;
  ciLow?: number;
  ciHigh?: number;
  factuality: number;
  reasoning: number;
  instructionFollowing: number;
  formatCompliance: number;
  verbosity: number;
  costPerPrompt: number;
  latencyP50Ms: number;
  latencyP95Ms: number;
  nPrompts: number;
  nJudgeEmpty: number;
  nFallback: number;
  catFactualRecall: number;
  catMultiStepReasoning: number;
  catInstructionFollowing: number;
  catCodeGeneration: number;
  catSafetyCalibration: number;
  catHallucinationUnderUncertainty: number;
}

export interface ModelDifficultyRow {
  model: string;
  difficulty: "easy" | "medium" | "hard" | "expert";
  overallScore: number;
  factuality: number;
  reasoning: number;
  instructionFollowing: number;
  formatCompliance: number;
  verbosity: number;
  nPrompts: number;
}

export interface JudgeCalibrationRow {
  dim: string;
  nProbes: number;
  nRuns: number;
  bandHitRate: number;
  mae: number;
  testRetestStd: number;
  nParseFailures: number;
}
