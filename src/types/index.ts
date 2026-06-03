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
  catAdversarialEdgeCases: number;
}
