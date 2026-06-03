import { Fragment, useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, LabelList } from "recharts";
import { loadLeaderboard } from "../../lib/loadCsv";
import { ModelPerformance } from "../../types";
import { buildModelColors, modelDisplayName } from "../../lib/modelColors";

const CATEGORIES: { key: keyof ModelPerformance; label: string }[] = [
  { key: "catFactualRecall", label: "Factual recall" },
  { key: "catMultiStepReasoning", label: "Multi-step reasoning" },
  { key: "catInstructionFollowing", label: "Instruction following" },
  { key: "catCodeGeneration", label: "Code generation" },
  { key: "catAdversarialEdgeCases", label: "Adversarial / edge cases" },
];

function CategoryBars({ row, color }: { row: ModelPerformance; color: string }) {
  const data = CATEGORIES.map((c) => ({
    name: c.label,
    score: ((row[c.key] as number) ?? 0) * 100,
  }));
  return (
    <div className="w-full h-[160px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart layout="vertical" data={data} margin={{ top: 4, right: 40, left: 0, bottom: 4 }}>
          <XAxis type="number" hide domain={[0, 100]} />
          <YAxis
            type="category"
            dataKey="name"
            stroke="#C8C2B8"
            fontSize={11}
            width={170}
            tickLine={false}
            axisLine={false}
          />
          <Bar dataKey="score" fill={color} radius={[0, 3, 3, 0]} barSize={12}>
            <LabelList
              dataKey="score"
              position="right"
              fill="#F5F0E8"
              fontSize={11}
              formatter={(v: number) => v.toFixed(1)}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function LeaderboardTable() {
  const [data, setData] = useState<ModelPerformance[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadLeaderboard().then(setData);
  }, []);

  if (!data.length) return null;

  const colors = buildModelColors(data.map((d) => d.model));

  const bestFactuality = Math.max(...data.map((d) => d.factuality));
  const bestReasoning = Math.max(...data.map((d) => d.reasoning));
  const bestInstruction = Math.max(...data.map((d) => d.instructionFollowing));
  const bestFormat = Math.max(...data.map((d) => d.formatCompliance));
  const bestLatency = Math.min(...data.map((d) => d.latencyP50Ms));

  const toggle = (model: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(model)) next.delete(model);
      else next.add(model);
      return next;
    });
  };

  const fmt = (n: number, d = 1) => (n * 100).toFixed(d);
  const fmtCi = (lo?: number, hi?: number) =>
    lo !== undefined && hi !== undefined ? `[${(lo * 100).toFixed(1)} – ${(hi * 100).toFixed(1)}]` : "—";

  return (
    <div className="w-full max-w-5xl mx-auto bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-8 border border-white/[0.06] shadow-2xl overflow-x-auto">
      <table className="w-full text-left border-collapse min-w-[920px]">
        <thead className="border-b border-white/[0.1]">
          <tr className="text-[#F5F0E8] text-[10px] uppercase tracking-[0.12em]">
            <th className="pb-4 pr-2 font-semibold w-8"></th>
            <th className="pb-4 pr-2 font-semibold text-right w-10">Rank</th>
            <th className="pb-4 font-semibold">Model</th>
            <th className="pb-4 font-semibold text-right">Overall</th>
            <th className="pb-4 font-semibold text-right">Factuality</th>
            <th className="pb-4 font-semibold text-right">Reasoning</th>
            <th className="pb-4 font-semibold text-right">Instruct</th>
            <th className="pb-4 font-semibold text-right">Format</th>
            <th className="pb-4 font-semibold text-right pl-4">Latency P50</th>
            <th className="pb-4 font-semibold text-right">Prompts</th>
            <th className="pb-4 font-semibold text-right">Fallbacks</th>
          </tr>
        </thead>
        <tbody className="text-[#C8C2B8] text-[13px]">
          {data.map((row) => {
            const isOpen = expanded.has(row.model);
            const color = colors.get(row.model) ?? "#C8873A";
            return (
              <Fragment key={row.model}>
                <tr
                  className="hover:bg-white/[0.03] transition-colors cursor-pointer border-b border-white/[0.04]"
                  onClick={() => toggle(row.model)}
                >
                  <td className="py-4 pr-2 text-[#C8C2B8] select-none">
                    <span className={`inline-block transition-transform ${isOpen ? "rotate-90" : ""}`}>›</span>
                  </td>
                  <td className="py-4 pr-2 text-right text-[#F5F0E8] font-mono">{row.rank}</td>
                  <td className="py-4 text-[#F5F0E8] font-medium pr-4" title={row.model}>
                    {modelDisplayName(row.model)}
                  </td>
                  <td className="py-4 px-4 text-right">
                    <div className="text-[#C8873A] font-medium">{fmt(row.overallScore)}</div>
                    <div className="text-[10px] text-[#C8C2B8]/70 font-mono mt-0.5">{fmtCi(row.ciLow, row.ciHigh)}</div>
                  </td>
                  <td className="py-4 px-4 text-right">
                    <span className={row.factuality === bestFactuality ? "border-b border-[#F5F0E8] text-[#F5F0E8]" : ""}>
                      {fmt(row.factuality)}
                    </span>
                  </td>
                  <td className="py-4 px-4 text-right">
                    <span className={row.reasoning === bestReasoning ? "border-b border-[#F5F0E8] text-[#F5F0E8]" : ""}>
                      {fmt(row.reasoning)}
                    </span>
                  </td>
                  <td className="py-4 px-4 text-right">
                    <span className={row.instructionFollowing === bestInstruction ? "border-b border-[#F5F0E8] text-[#F5F0E8]" : ""}>
                      {fmt(row.instructionFollowing)}
                    </span>
                  </td>
                  <td className="py-4 px-4 text-right">
                    <span className={row.formatCompliance === bestFormat ? "border-b border-[#F5F0E8] text-[#F5F0E8]" : ""}>
                      {fmt(row.formatCompliance)}
                    </span>
                  </td>
                  <td className="py-4 pr-4 pl-4 text-right font-mono">
                    <span className={row.latencyP50Ms === bestLatency ? "border-b border-[#F5F0E8] text-[#F5F0E8]" : ""}>
                      {Math.round(row.latencyP50Ms)}ms
                    </span>
                  </td>
                  <td className="py-4 px-4 text-right font-mono">{row.nPrompts}</td>
                  <td className="py-4 px-4 text-right font-mono">{row.nFallback}</td>
                </tr>
                {isOpen && (
                  <tr className="bg-white/[0.02]">
                    <td colSpan={11} className="py-5 px-4">
                      <div className="grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-6">
                        <div className="space-y-2">
                          <div className="text-[10px] uppercase tracking-[0.12em] text-[#F5F0E8]">Strict overall</div>
                          <div className="text-[#C8873A] text-[20px] font-display">
                            {row.overallStrict !== undefined ? fmt(row.overallStrict) : "—"}
                          </div>
                          <div className="text-[11px] text-[#C8C2B8]/75 leading-relaxed">
                            NaN dimensions imputed with model's own mean.
                          </div>
                          <div className="pt-3 text-[10px] uppercase tracking-[0.12em] text-[#F5F0E8]">Judge / fallback</div>
                          <div className="text-[11px] text-[#C8C2B8] font-mono">
                            judge empty: {row.nJudgeEmpty} · fallback: {row.nFallback} / {row.nPrompts}
                          </div>
                        </div>
                        <div>
                          <div className="text-[10px] uppercase tracking-[0.12em] text-[#F5F0E8] mb-2">Category breakdown</div>
                          <CategoryBars row={row} color={color} />
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      <div className="mt-4 space-y-2 max-w-3xl">
        <p className="text-[11px] text-[#C8C2B8]/65 leading-relaxed">
          Latency p95 excluded — on free-tier OpenRouter, tail latency reflects provider queue depth, not model inference speed.
        </p>
        <p className="text-[11px] text-[#C8C2B8]/65 leading-relaxed">
          Overall = mean of the four dimension scores (factuality, reasoning, instruction following, format compliance), each averaged across all applicable prompts and rescaled to 0–100. The 95% CI is a bootstrap over per-prompt scores.
        </p>
      </div>
    </div>
  );
}
