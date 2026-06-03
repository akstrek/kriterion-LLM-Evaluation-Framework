import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip, Legend, Cell, LabelList,
} from "recharts";
import { loadLeaderboardByDifficulty } from "../../lib/loadCsv";
import { ModelDifficultyRow } from "../../types";
import { buildModelColors, modelDisplayName } from "../../lib/modelColors";
import { useIsMobile } from "../../lib/useIsMobile";

const TIERS: ModelDifficultyRow["difficulty"][] = ["easy", "medium", "hard", "expert"];

const Tip = ({ active, payload, label }: any) => {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="bg-[rgba(10,8,6,0.92)] backdrop-blur-md border border-white/10 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-[#F5F0E8] text-[12px] font-medium capitalize mb-1">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} className="text-[11px] font-mono" style={{ color: p.color }}>
          {p.dataKey}: {Number(p.value).toFixed(1)}
        </p>
      ))}
    </div>
  );
};

export function DifficultyBreakdown() {
  const [rows, setRows] = useState<ModelDifficultyRow[]>([]);
  const isMobile = useIsMobile();

  useEffect(() => {
    loadLeaderboardByDifficulty().then(setRows);
  }, []);

  if (!rows.length) return null;

  const models: string[] = Array.from(new Set<string>(rows.map((r) => r.model)));
  const colors = buildModelColors(models);

  // Pivot to one row per difficulty tier with model columns holding overallScore × 100.
  const chartData = TIERS.map((tier) => {
    const row: any = { difficulty: tier };
    for (const m of models) {
      const match = rows.find((r) => r.model === m && r.difficulty === tier);
      row[modelDisplayName(m)] = match ? +(match.overallScore * 100).toFixed(2) : null;
    }
    return row;
  });

  return (
    <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-4 sm:p-6 md:p-8 border border-white/[0.06] shadow-2xl">
      <div className="flex items-baseline justify-between mb-3">
        <h3 className="text-[#F5F0E8] text-[16px] font-display">Difficulty Breakdown</h3>
        <span className="text-[10px] uppercase tracking-[0.12em] text-[#C8C2B8]/65">overall_applicable × tier</span>
      </div>
      <p className="text-[11px] text-[#C8C2B8]/65 leading-relaxed mb-4 max-w-2xl">
        The headline mixes 100 prompts at each difficulty tier into one mean. Here the same scores are split by tier — the expert column is the one that tends to separate models.
      </p>
      <div className="w-full h-[320px] sm:h-[340px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }} barCategoryGap="22%">
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="difficulty" stroke="#F5F0E8" fontSize={isMobile ? 10 : 11} tickLine={false} axisLine={false} />
            <YAxis domain={[0, 100]} stroke="#C8C2B8" fontSize={11} tickLine={false} axisLine={false} width={36} />
            <Tooltip content={<Tip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
            <Legend wrapperStyle={{ fontSize: isMobile ? "10px" : "12px", color: "#F5F0E8", paddingTop: 8 }} iconType="circle" />
            {models.map((m) => {
              const c = colors.get(m) ?? "#C8873A";
              const display = modelDisplayName(m);
              return (
                <Bar key={m} dataKey={display} fill={c} radius={[3, 3, 0, 0]}>
                  {chartData.map((_, i) => (
                    <Cell key={i} fill={c} />
                  ))}
                  {!isMobile && (
                    <LabelList
                      dataKey={display}
                      position="top"
                      fill="#F5F0E8"
                      fontSize={10}
                      formatter={(v: number) => (typeof v === "number" ? v.toFixed(0) : "")}
                    />
                  )}
                </Bar>
              );
            })}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
