import * as React from "react";
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

// Provider glyphs: simple-icons SVG paths for openai/google/nvidia, monogram
// for moonshotai (no simple-icons entry). All paths use viewBox 0 0 24 24 and
// fill currentColor so they inherit the chip's text colour.
type ProviderKind = "M" | "G" | "O" | "N";

function ProviderGlyph({ kind }: { kind: ProviderKind }) {
  if (kind === "O") {
    return (
      <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true" className="text-[#C8C2B8]">
        <path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z" />
      </svg>
    );
  }
  if (kind === "G") {
    return (
      <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true" className="text-[#C8C2B8]">
        <path d="M12.545 10.239v3.821h5.445c-.712 2.315-2.647 3.972-5.445 3.972a6.033 6.033 0 110-12.064c1.498 0 2.866.549 3.921 1.453l2.814-2.814A9.969 9.969 0 0012.545 2C7.021 2 2.543 6.477 2.543 12s4.478 10 10.002 10c8.396 0 10.249-7.85 9.426-11.748l-9.426-.013z" />
      </svg>
    );
  }
  if (kind === "N") {
    return (
      <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true" className="text-[#C8C2B8]">
        <path d="M8.948 8.798v-1.43a6.7 6.7 0 0 1 .424-.018c3.922-.123 6.493 3.374 6.493 3.374s-2.774 3.851-5.75 3.851c-.398 0-.787-.062-1.158-.185v-4.346c1.528.185 1.837.857 2.747 2.385l2.04-1.714s-1.493-1.961-4.002-1.961c-.27-.003-.534.015-.794.044zm0-4.726v2.138c.142-.013.284-.024.424-.029 5.45-.185 9.013 4.473 9.013 4.473s-4.083 4.973-8.331 4.973c-.379 0-.74-.034-1.107-.092v1.327c.308.038.61.061.918.061 3.957 0 6.811-2.022 9.572-4.413.458.367 2.337 1.262 2.726 1.654-2.625 2.199-8.741 3.969-12.232 3.969-.336 0-.659-.02-.978-.052v1.875h15.027V4.072H8.948zm0 10.314v1.126c-3.654-.654-4.668-4.453-4.668-4.453s1.756-1.943 4.668-2.255v1.235l-.006-.001c-1.527-.185-2.728 1.247-2.728 1.247s.677 2.418 2.734 3.101zm-6.42-3.471s2.165-3.201 6.42-3.524v-1.149c-4.71.379-8.794 4.366-8.794 4.366s2.312 6.687 8.794 7.299v-1.219c-4.758-.598-6.42-5.773-6.42-5.773z" />
      </svg>
    );
  }
  return <span className="text-[#C8C2B8] text-[11px] font-mono font-bold">{kind}</span>;
}

// ── Model card data + render ────────────────────────────────────────────────
// Four compound cards: Judge + 3 Evaluators. Each primary card has its
// fallback collapsed inside it, expandable on click. google/gemma-4-31b-it
// carries dual badges (Evaluator + Evaluator Fallback) because it serves
// as BOTH a primary evaluator AND as the fallback for openai/gpt-oss-120b.
// The gpt-oss-120b card's fallback section is a cross-reference back to the
// gemma card rendered above (no duplicate render).

type CardRole = "judge" | "judgeFallback" | "evaluator" | "evaluatorFallback";
type ArchType = "MoE" | "Dense" | "Hybrid" | "LatentMoE";

interface ModelData {
  displayName: string;
  primaryId: string;
  provider: string;
  providerKind: ProviderKind;
  parameters: string;
  oneLiner: string;
  architecturalHighlight: string;
  architectureType: ArchType;
  huggingFaceUrl: string;
}

interface PrimaryCardData extends ModelData {
  role: "judge" | "evaluator";
  secondaryRole?: "evaluatorFallback";
  alsoFallbackFor?: string;
  fallbackRole?: CardRole;
  inlineFallback?: ModelData;
  crossRefFallback?: { displayName: string; primaryId: string };
}

// ROLE BADGE — base styles plus group-hover amplification so the badge
// gains contrast at the exact moment the user is about to commit to a click.
const ROLE_BADGE_STYLES: Record<CardRole, string> = {
  judge:
    "bg-[#C8873A]/20 border border-[#C8873A]/40 text-[#F5C387] " +
    "group-hover:bg-[#C8873A]/30 group-hover:border-[#C8873A]/75 group-hover:text-[#FCD3A0]",
  judgeFallback:
    "bg-[#C8873A]/10 border border-[#C8873A]/25 text-[#F5C387]/70 " +
    "group-hover:bg-[#C8873A]/20 group-hover:border-[#C8873A]/50 group-hover:text-[#F5C387]/95",
  evaluator:
    "bg-white/[0.08] border border-white/[0.18] text-[#F5F0E8] " +
    "group-hover:bg-white/[0.14] group-hover:border-white/[0.30]",
  evaluatorFallback:
    "bg-white/[0.04] border border-white/[0.10] text-[#C8C2B8] " +
    "group-hover:bg-white/[0.08] group-hover:border-white/[0.20] group-hover:text-[#F5F0E8]",
};

const ROLE_BADGE_LABELS: Record<CardRole, string> = {
  judge:             "Judge",
  judgeFallback:     "Judge Fallback",
  evaluator:         "Evaluator",
  evaluatorFallback: "Evaluator Fallback",
};

function RoleBadge({ role }: { role: CardRole }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded-md text-[9px] uppercase tracking-[0.15em] font-mono font-medium transition-colors duration-200 ${ROLE_BADGE_STYLES[role]}`}>
      {ROLE_BADGE_LABELS[role]}
    </span>
  );
}

function ArchPill({ type }: { type: ArchType }) {
  return (
    <span className="inline-block px-1.5 py-0.5 rounded bg-white/[0.06] border border-white/[0.10] text-[#F5F0E8]/80 text-[10px] tracking-wide font-mono mx-1 align-baseline">
      {type}
    </span>
  );
}

function CollapsiblePre({ preview, full, headerLeft, headerRight }: { preview: string; full: string; headerLeft: string; headerRight: string }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] overflow-hidden mb-4">
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]">
        <span className="text-[10px] uppercase tracking-[0.15em] text-[#C8C2B8]">{headerLeft}</span>
        <span className="text-[10px] text-[#C8C2B8] font-mono">{headerRight}</span>
      </div>
      <pre className="px-5 pt-4 pb-2 text-[11px] text-[#C8C2B8] font-mono leading-relaxed whitespace-pre-wrap overflow-x-auto">{open ? full : preview}</pre>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-center gap-2 py-2.5 border-t border-white/[0.04] hover:bg-white/[0.025] transition-colors cursor-pointer"
      >
        <span className="text-[9px] uppercase tracking-widest text-[#C8C2B8]/70 font-mono">{open ? "hide full rubric" : "show full rubric"}</span>
        <ChevronDown className={`text-[#C8C2B8]/70 transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
    </div>
  );
}

function ChevronDown({ className = "" }: { className?: string }) {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
      <path d="M2 3.5L5 6.5L8 3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

// InlinedFallback — full fallback content rendered inside the parent primary card
// when the user expands the toggle. Visually subordinate via reduced padding,
// muted background, and dimmed opacity.
const InlinedFallback: React.FC<{ data: ModelData; role: CardRole; parentName: string }> = ({ data, role, parentName }) => {
  return (
    <div className="group/fallback relative mt-3 -mx-5 -mb-5 px-5 pt-4 pb-5 bg-black/30 border-t border-white/[0.06] rounded-b-2xl">
      {/* fallback HF link — same hover-arrow-chip pattern as the primary card */}
      <a
        href={data.huggingFaceUrl}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`Open ${data.displayName} on HuggingFace`}
        onClick={(e) => e.stopPropagation()}
        className="absolute top-3 right-3 w-6 h-6 rounded-full bg-white flex items-center justify-center opacity-40 group-hover/fallback:opacity-100 hover:scale-110 transition-all duration-200"
      >
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M2.5 7.5L7.5 2.5M7.5 2.5H3.5M7.5 2.5V6.5" stroke="#0A0806" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </a>

      <div className="flex flex-wrap items-center gap-2 mb-3 pr-10">
        <RoleBadge role={role} />
        <span className="text-[10px] text-[#C8C2B8]/70 font-mono">↳ fallback for {parentName}</span>
      </div>

      <div className="flex items-start gap-3 mb-3">
        <div className="flex-shrink-0 w-7 h-7 rounded-lg bg-white/[0.04] border border-white/[0.08] flex items-center justify-center mt-0.5">
          <ProviderGlyph kind={data.providerKind} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[#F5F0E8] text-[12px] font-semibold leading-tight">{data.displayName}</p>
          <p className="text-[#C8C2B8] text-[10px] font-mono mt-0.5 truncate">{data.primaryId}</p>
        </div>
      </div>

      <p className="text-[#C8C2B8] text-[11px] font-mono mb-2">
        Provider: {data.provider}  |  Parameters: {data.parameters}
      </p>
      <p className="text-[#C8C2B8] text-[12px] leading-relaxed mb-2">{data.oneLiner}</p>
      <p className="text-[#C8C2B8] text-[12px] leading-relaxed">
        <span className="text-[#F5F0E8] text-[10px] uppercase tracking-[0.15em] font-medium">Architectural Highlight</span>
        <ArchPill type={data.architectureType} />
        {data.architecturalHighlight}
      </p>
    </div>
  );
};

const ModelCard: React.FC<{ data: PrimaryCardData }> = ({ data }) => {
  const [expanded, setExpanded] = React.useState(false);
  const hasInline = !!data.inlineFallback;
  const hasCrossRef = !!data.crossRefFallback;
  const fallbackId = data.inlineFallback?.primaryId ?? data.crossRefFallback?.primaryId;
  return (
    <div className="group relative bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5 transition-transform duration-200 hover:scale-[1.02]">
      {/* primary HF link — top-right hover-arrow */}
      <a
        href={data.huggingFaceUrl}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`Open ${data.displayName} on HuggingFace`}
        onClick={(e) => e.stopPropagation()}
        className="absolute top-3 right-3 w-6 h-6 rounded-full bg-white flex items-center justify-center opacity-40 group-hover:opacity-100 hover:scale-110 transition-all duration-200"
      >
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M2.5 7.5L7.5 2.5M7.5 2.5H3.5M7.5 2.5V6.5" stroke="#0A0806" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </a>

      {/* role badges */}
      <div className="flex flex-wrap items-center gap-2 mb-3 pr-10">
        <RoleBadge role={data.role} />
        {data.secondaryRole && <RoleBadge role={data.secondaryRole} />}
      </div>

      {data.alsoFallbackFor && (
        <p className="text-[11px] text-[#F5C387]/80 mb-3 leading-snug">
          Dual-role — primary evaluator <span className="text-[#C8C2B8]">and</span> fallback for {data.alsoFallbackFor}.
        </p>
      )}

      {/* provider chip + name + id */}
      <div className="flex items-start gap-3 mb-3">
        <div className="flex-shrink-0 w-7 h-7 rounded-lg bg-white/[0.04] border border-white/[0.08] flex items-center justify-center mt-0.5">
          <ProviderGlyph kind={data.providerKind} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[#F5F0E8] text-[13px] font-semibold leading-tight">{data.displayName}</p>
          <p className="text-[#C8C2B8] text-[10px] font-mono mt-0.5 truncate">{data.primaryId}</p>
        </div>
      </div>

      <p className="text-[#C8C2B8] text-[11px] font-mono mb-3">
        Provider: {data.provider}  |  Parameters: {data.parameters}
      </p>
      <p className="text-[#C8C2B8] text-[12px] leading-relaxed mb-3">{data.oneLiner}</p>
      <p className="text-[#C8C2B8] text-[12px] leading-relaxed">
        <span className="text-[#F5F0E8] text-[10px] uppercase tracking-[0.15em] font-medium">Architectural Highlight</span>
        <ArchPill type={data.architectureType} />
        {data.architecturalHighlight}
      </p>

      {/* expandable fallback toggle (inline data) */}
      {hasInline && data.fallbackRole && (
        <>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            className="w-full flex items-center gap-2 pt-3 mt-3 px-5 pb-3 border-t border-white/[0.04] cursor-pointer hover:bg-white/[0.025] transition-colors -mx-5 -mb-5 rounded-b-2xl"
          >
            <span className="text-[9px] uppercase tracking-widest text-[#C8C2B8]/60 font-mono">fallback →</span>
            <span className="text-[#C8C2B8] text-[10px] font-mono truncate flex-1 text-left">{fallbackId}</span>
            <span className="text-[9px] uppercase tracking-widest text-[#C8C2B8]/40 font-mono">{expanded ? "hide" : "show"}</span>
            <ChevronDown className={`text-[#C8C2B8]/60 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} />
          </button>
          {expanded && (
            <InlinedFallback data={data.inlineFallback!} role={data.fallbackRole} parentName={data.displayName} />
          )}
        </>
      )}

      {/* cross-reference fallback (no expand — points to a card rendered above) */}
      {hasCrossRef && (
        <div className="flex items-center gap-2 pt-3 mt-3 border-t border-white/[0.04]">
          <span className="text-[9px] uppercase tracking-widest text-[#C8C2B8]/60 font-mono">fallback →</span>
          <span className="text-[#C8C2B8] text-[10px] font-mono truncate flex-1">{data.crossRefFallback!.primaryId}</span>
          <span className="text-[10px] text-[#C8C2B8]/70">(↑ see card above)</span>
        </div>
      )}
    </div>
  );
};

const MODEL_CARDS: PrimaryCardData[] = [
  // ── JUDGE ──────────────────────────────────────────────────────────────────
  {
    displayName: "NVIDIA Nemotron 3 Super 120B",
    primaryId: "nvidia/nemotron-3-super-120b-a12b:free",
    role: "judge",
    provider: "NVIDIA",
    providerKind: "N",
    parameters: "120B total, 12B active",
    oneLiner: "NVIDIA's flagship open-weight reasoning model with a 1M-token context window.",
    architecturalHighlight: "Mamba-2 + MoE + Attention with Multi-Token Prediction (MTP). LatentMoE projects tokens into a smaller latent dimension, calling 4 experts for the cost of 1.",
    architectureType: "LatentMoE",
    huggingFaceUrl: "https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8",
    fallbackRole: "judgeFallback",
    inlineFallback: {
      displayName: "NVIDIA Nemotron 3 Nano 30B",
      primaryId: "nvidia/nemotron-3-nano-30b-a3b:free",
      provider: "NVIDIA",
      providerKind: "N",
      parameters: "31.6B total, 3.2B active",
      oneLiner: "NVIDIA's compact hybrid MoE backup judge with a 1M-token context window.",
      architecturalHighlight: "Hybrid Mamba-2 + Transformer MoE with 128 granular experts, top-6 routing. 23 Mamba-2 + 23 MoE + 6 Attention layers.",
      architectureType: "Hybrid",
      huggingFaceUrl: "https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16",
    },
  },
  // ── EVALUATOR 1 — Kimi ─────────────────────────────────────────────────────
  {
    displayName: "Moonshot AI Kimi K2.6",
    primaryId: "moonshotai/kimi-k2.6:free",
    role: "evaluator",
    provider: "Moonshot AI",
    providerKind: "M",
    parameters: "1T total, 32B active",
    oneLiner: "Moonshot AI's open-source native multimodal agentic model with a 256K context window.",
    architecturalHighlight: "384 experts, 8 selected per token plus 1 shared expert. Multi-Latent Attention with SwiGLU.",
    architectureType: "MoE",
    huggingFaceUrl: "https://huggingface.co/moonshotai/Kimi-K2.6",
    fallbackRole: "evaluatorFallback",
    inlineFallback: {
      displayName: "Google Gemma 4 26B-A4B-IT",
      primaryId: "google/gemma-4-26b-a4b-it:free",
      provider: "Google",
      providerKind: "G",
      parameters: "26B total, 4B active",
      oneLiner: "Google's efficient MoE Gemma variant under Apache 2.0 with a 256K context window.",
      architecturalHighlight: "128 fine-grained experts, top-8 routing, custom GELU FFN. Dual sliding-window plus global attention.",
      architectureType: "MoE",
      huggingFaceUrl: "https://huggingface.co/google/gemma-4-26B-A4B-it",
    },
  },
  // ── EVALUATOR 2 — Gemma 4 31B (dual-role: also fallback for GPT-OSS 120B) ──
  {
    displayName: "Google Gemma 4 31B-IT",
    primaryId: "google/gemma-4-31b-it:free",
    role: "evaluator",
    secondaryRole: "evaluatorFallback",
    alsoFallbackFor: "GPT-OSS 120B",
    provider: "Google",
    providerKind: "G",
    parameters: "31B dense (all parameters active)",
    oneLiner: "Google's flagship dense Gemma 4 model — built on the Gemini 3 architecture with a ~550M vision encoder.",
    architecturalHighlight: "Sliding-window (1024 tokens) plus global full attention. Proportional RoPE for 256K context coherence.",
    architectureType: "Dense",
    huggingFaceUrl: "https://huggingface.co/google/gemma-4-31B-it",
    fallbackRole: "evaluatorFallback",
    inlineFallback: {
      displayName: "OpenAI GPT-OSS 20B",
      primaryId: "openai/gpt-oss-20b:free",
      provider: "OpenAI",
      providerKind: "O",
      parameters: "21B total, 3.6B active",
      oneLiner: "OpenAI's compact open-weight MoE that fits in 16GB VRAM under Apache 2.0, 128K context.",
      architecturalHighlight: "32 experts per layer, top-4 routing, MXFP4 quantization.",
      architectureType: "MoE",
      huggingFaceUrl: "https://huggingface.co/openai/gpt-oss-20b",
    },
  },
  // ── EVALUATOR 3 — GPT-OSS 120B (fallback is gemma-4-31b → cross-ref above) ─
  {
    displayName: "OpenAI GPT-OSS 120B",
    primaryId: "openai/gpt-oss-120b:free",
    role: "evaluator",
    provider: "OpenAI",
    providerKind: "O",
    parameters: "117B total, 5.1B active",
    oneLiner: "OpenAI's flagship open-weight MoE, MXFP4-quantized to run on a single H100, 128K context.",
    architecturalHighlight: "128 experts per layer, top-4 routing, alternating dense plus sparse attention with learned attention sinks.",
    architectureType: "MoE",
    huggingFaceUrl: "https://huggingface.co/openai/gpt-oss-120b",
    crossRefFallback: {
      displayName: "Gemma 4 31B-IT",
      primaryId: "google/gemma-4-31b-it:free",
    },
  },
];

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
              <p className="text-[#F5F0E8] text-[14px] leading-relaxed max-w-[600px]">
                <span className="font-mono text-[#F5C387]">1,200</span> API calls. <span className="font-mono text-[#F5C387]">4</span> architecturally independent models. Two open-source rate-limiting algorithms from <span className="font-mono text-[#F5C387]">1996</span> and <span className="font-mono text-[#F5C387]">2002</span>. Total cost: <span className="font-mono text-[#F5C387]">$0</span>.
              </p>
            </div>
          </motion.div>

          {/* The Architecture, 30-second pitch */}
          <motion.div custom={0.5} variants={fadeUp} initial="hidden" animate="show" className="mb-10">
            <SectionLabel>The Architecture</SectionLabel>
            <h3 className="font-display text-[#F5F0E8] text-[22px] font-bold tracking-tight mb-5">
              Traffic Shaping the Free Tier
            </h3>
            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5 space-y-4">
              <p className="text-[10px] uppercase tracking-[0.2em] text-[#C8C2B8]/70 font-medium">
                Before the methodology — the constraint that shaped every decision below
              </p>
              <p className="text-[#F5F0E8] text-[14px] leading-relaxed font-semibold">
                Treated as network traffic shaping, not rate-limit accounting.
              </p>
              <p className="text-[#C8C2B8] text-[13px] leading-relaxed">
                The OpenRouter free tier is a hard-capped multi-tenant resource: 20 RPM, 1000 RPD, no paid fallback. The disciplined port borrows the toolkit Linux uses for network qdiscs.
              </p>

              {/* HTB tree visual — concrete picture of the abstract pill below */}
              <div className="bg-white/[0.03] rounded-lg p-4 border border-white/[0.05]">
                <p className="text-[10px] uppercase tracking-[0.15em] text-[#C8C2B8]/70 mb-3 font-medium">HTB tree — leaf width ∝ RPD share</p>
                <div className="overflow-x-auto -mx-1">
                <svg viewBox="0 0 480 130" preserveAspectRatio="xMidYMid meet" aria-hidden="true" className="min-w-[440px] w-full h-auto overflow-visible">
                  {/* root */}
                  <rect x="180" y="6" width="120" height="26" rx="6" fill="rgba(245,195,135,0.12)" stroke="rgba(245,195,135,0.45)" />
                  <text x="240" y="23" textAnchor="middle" fontFamily="ui-monospace, monospace" fontSize="11" fill="#F5C387">root · 950 RPD</text>
                  {/* connectors */}
                  <path d="M240 32 L240 50 M70 50 L410 50 M70 50 L70 64 M180 50 L180 64 M290 50 L290 64 M410 50 L410 64" stroke="rgba(245,240,232,0.25)" strokeWidth="1" fill="none" />
                  {/* leaves — widths proportional to RPD: nvidia 300, openai 163, moonshotai 163, google 325 */}
                  <rect x="14" y="64" width="112" height="26" rx="5" fill="rgba(245,240,232,0.05)" stroke="rgba(245,240,232,0.18)" />
                  <text x="70" y="81" textAnchor="middle" fontFamily="ui-monospace, monospace" fontSize="10" fill="#F5F0E8">nvidia · 300</text>
                  <text x="70" y="106" textAnchor="middle" fontFamily="ui-monospace, monospace" fontSize="9" fill="#C8C2B8">judge</text>

                  <rect x="119" y="64" width="61" height="26" rx="5" fill="rgba(245,240,232,0.05)" stroke="rgba(245,240,232,0.18)" />
                  <text x="150" y="81" textAnchor="middle" fontFamily="ui-monospace, monospace" fontSize="10" fill="#F5F0E8">openai · 163</text>
                  <text x="150" y="106" textAnchor="middle" fontFamily="ui-monospace, monospace" fontSize="9" fill="#C8C2B8">gpt-oss</text>

                  <rect x="229" y="64" width="61" height="26" rx="5" fill="rgba(245,240,232,0.05)" stroke="rgba(245,240,232,0.18)" />
                  <text x="260" y="81" textAnchor="middle" fontFamily="ui-monospace, monospace" fontSize="10" fill="#F5F0E8">moon · 163</text>
                  <text x="260" y="106" textAnchor="middle" fontFamily="ui-monospace, monospace" fontSize="9" fill="#C8C2B8">kimi</text>

                  <rect x="289" y="64" width="121" height="26" rx="5" fill="rgba(245,240,232,0.05)" stroke="rgba(245,240,232,0.18)" />
                  <text x="349" y="81" textAnchor="middle" fontFamily="ui-monospace, monospace" fontSize="10" fill="#F5F0E8">google · 325</text>
                  <text x="349" y="106" textAnchor="middle" fontFamily="ui-monospace, monospace" fontSize="9" fill="#C8C2B8">gemma + landing pad</text>

                  <text x="240" y="126" textAnchor="middle" fontFamily="ui-monospace, monospace" fontSize="9" fill="rgba(200,194,184,0.6)">idle siblings lend tokens up to root</text>
                </svg>
                </div>
              </div>

              <div className="space-y-2">
                {[
                  { pill: "HTB",     cite: "Devera, 2002",                text: "Hierarchical Token Bucket — root quota refills continuously; providers borrow when siblings idle." },
                  { pill: "DRR",     cite: "Shreedhar & Varghese, 1996",  text: "Deficit Round Robin schedules per-model fairness; throttled lanes never starve siblings." },
                  { pill: "Split",   cite: "650 + 300 RPD",               text: "Judge and evaluator hold separate guaranteed shares of the daily quota." },
                  { pill: "Backoff", cite: "TCP-style",                   text: "429-burst halves root rate for a 5-minute cooldown, then restores automatically." },
                ].map((b) => (
                  <div key={b.pill} className="flex items-start gap-3 bg-white/[0.03] rounded-lg p-3 border border-white/[0.05]">
                    <div className="flex-shrink-0 flex flex-col items-start gap-1 min-w-[88px]">
                      <Pill>{b.pill}</Pill>
                      <span className="text-[9px] uppercase tracking-widest text-[#C8C2B8]/60 font-mono leading-tight">{b.cite}</span>
                    </div>
                    <p className="text-[#C8C2B8] text-[12px] leading-relaxed flex-1 pt-0.5">{b.text}</p>
                  </div>
                ))}
              </div>

              {/* tc-htb thesis callout + $0 mic drop */}
              <div className="flex flex-wrap items-center gap-3 bg-[#C8873A]/10 border border-[#C8873A]/30 rounded-lg p-3">
                <span className="inline-block px-2 py-1 rounded-md bg-[#C8873A]/25 border border-[#C8873A]/50 text-[#FCD3A0] text-[11px] tracking-wide font-mono font-semibold">
                  tc-htb on API quota
                </span>
                <span className="text-[#F5F0E8] text-[13px] leading-relaxed flex-1 min-w-0 sm:min-w-[200px]">
                  The runner finishes flush with quota instead of crashing into it. <span className="font-mono text-[#F5C387]">$0</span> across 1,200 calls.
                </span>
              </div>
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
                <div className="grid grid-cols-[1fr_auto] sm:grid-cols-[1fr_auto_auto] text-[10px] uppercase tracking-[0.15em] text-[#C8C2B8] pb-3 border-b border-white/[0.06]">
                  <span>Category</span>
                  <span className="text-right pr-4 sm:pr-8">Count</span>
                  <span className="text-right hidden sm:inline">What it stresses</span>
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
                    className={`grid grid-cols-[1fr_auto] sm:grid-cols-[1fr_auto_auto] py-3 text-[13px] ${i < 4 ? "border-b border-white/[0.04]" : ""}`}
                  >
                    <span className="text-[#F5F0E8]">{row.cat}</span>
                    <span className="text-[#C8C2B8] font-mono text-[12px] text-right pr-4 sm:pr-8">{row.n}</span>
                    <span className="text-[#C8C2B8] text-[12px] text-right hidden sm:inline">{row.stress}</span>
                  </div>
                ))}
                <div className="grid grid-cols-[1fr_auto] sm:grid-cols-[1fr_auto_auto] py-3 border-t border-white/[0.08] mt-1">
                  <span className="text-[#F5F0E8] text-[13px] font-semibold">Total</span>
                  <span className="text-[#F5F0E8] font-mono text-[13px] font-semibold text-right pr-4 sm:pr-8">200</span>
                  <span className="text-[#C8C2B8] text-[12px] text-right hidden sm:inline">× 3 models = 600 responses</span>
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
                <span className="text-[#F5F0E8]">NVIDIA Nemotron 3 Super 120B</span> serves as the sole judge. 600 evaluator + 600 judge = <span className="font-mono text-[#F5F0E8]">1,200 calls</span>, <span className="font-mono text-[#F5F0E8]">2,400 dimensions</span> scored. Up to 2 retries plus 1 fallback hop on a degraded provider, all counted against the daily quota.
              </p>
            </div>

            <p className="text-[10px] uppercase tracking-[0.2em] text-[#C8C2B8] mb-3 font-medium">
              Free models used via single provider OpenRouter
            </p>

            <div className="space-y-3 mb-6">
              {MODEL_CARDS.map((data) => (
                <ModelCard key={`${data.primaryId}-${data.role}`} data={data} />
              ))}
            </div>

            <div className="flex items-start gap-3 border-l-2 border-white/[0.15] pl-4 mb-6">
              <p className="text-[#C8C2B8] text-[12px] leading-relaxed italic">
                Since all 3 evaluators are open-weight models accessed via a single provider, using any of them as judge introduces circularity — the judge must be architecturally independent from every model being evaluated.
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

            <CollapsiblePre
              headerLeft="Judge System Prompt"
              headerRight="JSON output only"
              preview={`Score this prompt-response pair. Use full 0.00-1.00 range — most responses
score 0.40-0.85, not 1.00.

factuality · reasoning · instruction_following · format_compliance
each scored 0.00–1.00 (or null when inapplicable).`}
              full={`Score this prompt-response pair. Use full 0.00-1.00 range — most responses
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
            />

            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5">
              <p className="text-[#C8C2B8] text-[12px] leading-relaxed mb-4">
                Nemotron scores all four dimensions in a single call, returning one JSON object per evaluator response. Dimensions the prompt does not exercise are returned as <code className="font-mono text-[#E8DFD2]">null</code> (no factual claims → null factuality; no inferential steps → null reasoning) and stored as NaN, so they are excluded from that row's <code className="font-mono text-[#E8DFD2]">overall_applicable</code> mean rather than penalised. Judge latency and token count are logged per call.
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
              HTB, DRR, and Atomic Writes
            </h3>

            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5 mb-3">
              <p className="text-[10px] uppercase tracking-[0.2em] text-[#C8C2B8] mb-3 font-medium">Hierarchical Token Bucket</p>
              <p className="text-[#C8C2B8] text-[13px] leading-relaxed mb-4">
                The Linux <span className="font-mono text-[#F5F0E8]">tc qdisc htb</span> primitive (Devera, 2002), applied to the OpenRouter quota. A root node holds the 18 RPM / 950 RPD ceiling. Provider leaves carry guaranteed shares — eval gets 650 RPD split across moonshotai, google, and openai; judge gets 300 RPD on nvidia. An idle sibling's tokens are borrowed up to the root cap (full HTB borrow semantics), so no leaf starves while another sits idle.
              </p>
              <pre className="bg-white/[0.03] rounded-lg p-3 border border-white/[0.05] text-[11px] text-[#C8C2B8] font-mono leading-relaxed overflow-x-auto">
{`root         18 RPM,  950 RPD       ← OpenRouter ceiling
 ├── nvidia       300 RPD            ← judge
 ├── openai       163 RPD            ← gpt-oss-120b
 ├── moonshotai   163 RPD            ← kimi-k2.6
 └── google       325 RPD            ← gemma + fallback landing pad

borrow: any leaf may consume idle siblings' tokens up to root`}
              </pre>
            </div>

            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5 mb-3">
              <p className="text-[10px] uppercase tracking-[0.2em] text-[#C8C2B8] mb-3 font-medium">Deficit Round Robin</p>
              <p className="text-[#C8C2B8] text-[13px] leading-relaxed">
                One FIFO queue per evaluator model; a DRR scheduler (Shreedhar &amp; Varghese, 1996) services them with a per-queue deficit counter and unit quantum. A producer thread fills a bounded pair-queue; three workers (one per evaluator) consume. The scheduler gates on the HTB so a throttled lane is skipped without consuming its quantum. Replaces the prior <span className="font-mono">ThreadPoolExecutor.as_completed</span> path that head-of-line-blocked on the slowest provider.
              </p>
            </div>

            {/* Compact strip — three subordinate concerns sharing one container, breaking the rhythm of the two big cards above */}
            <div className="bg-[rgba(10,8,6,0.45)] backdrop-blur-2xl rounded-2xl border border-white/[0.05] overflow-hidden">
              {[
                {
                  label: "Retry + Adaptive Throttle",
                  body: (<><span className="font-mono text-[#F5F0E8]">MAX_RETRY=2</span>, 30s delay. 429 counts against RPM and RPD, so a higher ceiling would burn quota. Trailing-60s 429 rate &gt; 30% halves the root for a 5-minute cooldown — TCP-style congestion response on API rate limits.</>),
                },
                {
                  label: "Atomic Checkpointing",
                  body: (<>Each result writes as a per-row parquet via <span className="font-mono text-[#F5F0E8]">tmp → fsync → os.replace</span> before the next call. Crashes lose ≤ one call. On startup the runner skips every <span className="font-mono text-[#F5F0E8]">(prompt_id, model)</span> already on disk.</>),
                },
                {
                  label: "Quota-Aware Self-Pacing",
                  body: (<>On quota exhaustion the runner stays in-process and sleeps to the next 00:01 UTC reset, polling every 5 min so it survives Windows suspend/resume. No external scheduler, no respawn.</>),
                },
              ].map((row, i, arr) => (
                <div
                  key={row.label}
                  className={`grid grid-cols-1 sm:grid-cols-[180px_1fr] gap-2 sm:gap-5 px-5 py-4 ${i < arr.length - 1 ? "border-b border-white/[0.04]" : ""}`}
                >
                  <p className="text-[10px] uppercase tracking-[0.18em] text-[#C8C2B8] font-medium pt-0.5">{row.label}</p>
                  <p className="text-[#C8C2B8] text-[12px] leading-relaxed">{row.body}</p>
                </div>
              ))}
            </div>
          </motion.div>

          <Divider />

          {/* Section 5, Leaderboard Columns */}
          <motion.div custom={8} variants={fadeUp} initial="hidden" animate="show">
            <SectionLabel>05, Leaderboard Schema</SectionLabel>
            <h3 className="font-display text-[#F5F0E8] text-[20px] font-bold tracking-tight mb-5">
              Two Aggregates, One Confidence Interval
            </h3>

            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5 mb-4">
              <p className="text-[#F5F0E8] text-[14px] leading-relaxed font-semibold mb-3">
                Two aggregates so you can't argue the ranking depends on how nulls are handled.
              </p>
              <p className="text-[#C8C2B8] text-[13px] leading-relaxed">
                Both computed from the same parquet, no tuning, no normalisation tricks. <span className="font-mono text-[#F5F0E8]">overall_applicable</span> is the row-wise mean of present (non-NaN) dimensions; <span className="font-mono text-[#F5F0E8]">overall_strict</span> imputes any NaN dimension with the model's own mean before averaging, so a model the judge could not score gets no free pass. A 95% bootstrap CI (1000× resample, pure numpy, zero quota impact) renders as error bars on <span className="font-mono">overall_applicable</span>.
              </p>
            </div>

            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                {[
                  { col: "overall_applicable",  desc: "Mean of present dims" },
                  { col: "overall_strict",      desc: "NaN dims imputed by model mean" },
                  { col: "ci_low / ci_high",    desc: "95% bootstrap CI (1000×)" },
                  { col: "avg_<dimension> × 4", desc: "Per-dimension mean (factuality, reasoning, instruction_…, format_…)" },
                  { col: "latency_p50_ms",      desc: "Milliseconds" },
                  { col: "latency_p95_ms",      desc: "Milliseconds" },
                  { col: "avg_tokens_used",     desc: "Per prompt" },
                  { col: "n_judge_empty",       desc: "Diagnostic count" },
                  { col: "n_fallback",          desc: "Diagnostic count" },
                  { col: "cat_<category>",      desc: "Per-category mean × 5" },
                ].map((item) => (
                  <div key={item.col} className="bg-white/[0.03] rounded-lg p-3 border border-white/[0.04]">
                    <p className="text-[#F5F0E8] text-[12px] font-mono mb-0.5">{item.col}</p>
                    <p className="text-[#C8C2B8] text-[11px]">{item.desc}</p>
                  </div>
                ))}
              </div>
              <p className="text-[#C8C2B8] text-[12px] leading-relaxed mt-4 pt-4 border-t border-white/[0.06]">
                <span className="text-[#F5F0E8] text-[11px] uppercase tracking-wider font-medium">Empty-judge handling  </span>
                When the judge returns an unparseable response, all four dimensions become NaN and <span className="font-mono">judge_empty=True</span> is recorded on the row. Previously, two of the four defaulted to 0.0 — a silent downward bias in the leaderboard. Calibration probes (HELM-style anchor responses) are noted as future work.
              </p>
            </div>
          </motion.div>

          <Divider />

          {/* Section 6, Defensibility */}
          <motion.div custom={9} variants={fadeUp} initial="hidden" animate="show">
            <SectionLabel>06, What Makes This Defensible</SectionLabel>
            <h3 className="font-display text-[#F5F0E8] text-[20px] font-bold tracking-tight mb-5">
              Three Properties That Separate a Benchmark from a Blog Post
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
              {[
                {
                  n: "01",
                  title: "External Judge",
                  blogPost: "Same family scores itself",
                  benchmark: "Judge shares no architecture, provider, or training lineage with any contestant. Self-preferencing bias (Zheng et al., 2023) eliminated; reasoning traces logged.",
                },
                {
                  n: "02",
                  title: "Deterministic Where Possible",
                  blogPost: "LLM judges every cell",
                  benchmark: "Format compliance runs regex and parser checks first; the LLM judge sees only genuinely ambiguous edge cases. Reproducible without re-running the judge.",
                },
                {
                  n: "03",
                  title: "Full Prompt Suite Published",
                  blogPost: "Cherry-picked screenshots",
                  benchmark: "All 200 prompts, expected output types, and ground truth labels ship with the repo. Swap the judge, add dimensions, rerun — no reverse-engineering required.",
                },
              ].map((item) => (
                <div
                  key={item.n}
                  className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] p-5 flex flex-col"
                >
                  <div className="flex items-baseline justify-between mb-3">
                    <p className="text-[#F5F0E8] text-[13px] font-semibold">{item.title}</p>
                    <span className="font-display text-[28px] font-black text-white/[0.07] leading-none">{item.n}</span>
                  </div>
                  <div className="mb-3 pb-3 border-b border-white/[0.05]">
                    <p className="text-[9px] uppercase tracking-[0.15em] text-[#C8C2B8]/60 mb-1 font-mono">Blog post</p>
                    <p className="text-[#C8C2B8]/70 text-[12px] leading-snug line-through decoration-[#C8C2B8]/30">{item.blogPost}</p>
                  </div>
                  <div>
                    <p className="text-[9px] uppercase tracking-[0.15em] text-[#F5C387]/80 mb-1 font-mono">Benchmark</p>
                    <p className="text-[#C8C2B8] text-[12px] leading-relaxed">{item.benchmark}</p>
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
                Nemotron 3 Super was selected because it is external to the evaluated set on the axes that matter: provider (NVIDIA vs. MoonshotAI vs. Google vs. OpenAI), training lineage (no known overlap with the Kimi, Gemma, or GPT-OSS post-training corpora), and access path (a separate provider on OpenRouter, not co-tenanted with any evaluator). The judge's reasoning traces are logged in full for every call, so the bias profile is auditable, not assumed away.
              </p>
            </div>
          </motion.div>

          {/* Footer — metric strip closer instead of "evaluation underway" */}
          <div className="pt-8 pb-2">
            <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl border border-white/[0.06] px-5 py-4">
              {[
                { v: "$0",    k: "total cost" },
                { v: "1,200", k: "API calls" },
                { v: "2,400", k: "dimensions scored" },
                { v: "0",     k: "crashes since HTB shipped" },
              ].map((m, i, arr) => (
                <React.Fragment key={m.k}>
                  <div className="flex items-baseline gap-2">
                    <span className="font-mono text-[#F5C387] text-[15px] font-semibold">{m.v}</span>
                    <span className="text-[#C8C2B8] text-[11px] uppercase tracking-[0.15em]">{m.k}</span>
                  </div>
                  {i < arr.length - 1 && <span className="text-[#C8C2B8]/30">·</span>}
                </React.Fragment>
              ))}
            </div>
          </div>
        </div>
      </ScrollableZone>

      <div className="pointer-events-auto">
        <BottomRight text="Design architecture for the Kriterion evaluation harness." />
      </div>
    </motion.div>
  );
}
