const FAMILY_COLORS: { match: RegExp; color: string }[] = [
  { match: /^google\//i, color: '#4285F4' },
  { match: /^openai\//i, color: '#10A37F' },
  { match: /^anthropic\//i, color: '#D97757' },
  { match: /^moonshotai\//i, color: '#A855F7' },
  { match: /^meta-llama\//i, color: '#6366F1' },
  { match: /^mistralai\//i, color: '#F97316' },
  { match: /^deepseek\//i, color: '#06B6D4' },
  { match: /^qwen\//i, color: '#EC4899' },
  { match: /^x-ai\//i, color: '#E11D48' },
  { match: /^cohere\//i, color: '#EAB308' },
];

const FALLBACK_PALETTE = [
  '#22D3EE',
  '#FACC15',
  '#34D399',
  '#F472B6',
  '#A78BFA',
  '#FB923C',
  '#60A5FA',
  '#F87171',
];

export function buildModelColors(models: string[]): Map<string, string> {
  const m = new Map<string, string>();
  let fallbackIdx = 0;
  for (const model of models) {
    const family = FAMILY_COLORS.find((f) => f.match.test(model));
    if (family) {
      m.set(model, family.color);
    } else {
      m.set(model, FALLBACK_PALETTE[fallbackIdx % FALLBACK_PALETTE.length]);
      fallbackIdx++;
    }
  }
  return m;
}

export function modelDisplayName(model: string): string {
  const stripped = model.replace(/:free$/, '');
  const slash = stripped.lastIndexOf('/');
  return slash >= 0 ? stripped.slice(slash + 1) : stripped;
}
