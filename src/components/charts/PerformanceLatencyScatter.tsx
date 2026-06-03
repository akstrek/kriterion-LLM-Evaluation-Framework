import { useEffect, useState } from "react";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Label,
  ErrorBar,
} from "recharts";
import { loadLeaderboard } from "../../lib/loadCsv";
import { ModelPerformance } from "../../types";
import { buildModelColors, modelDisplayName } from "../../lib/modelColors";

type ScatterRow = ModelPerformance & {
  ciErr: [number, number];
  latErr: [number, number];
};

const CustomTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const d = payload[0].payload as ScatterRow;
    const ci =
      d.ciLow !== undefined && d.ciHigh !== undefined
        ? `[${(d.ciLow * 100).toFixed(1)} – ${(d.ciHigh * 100).toFixed(1)}]`
        : "—";
    return (
      <div className="bg-[rgba(10,8,6,0.92)] backdrop-blur-md border border-white/10 rounded-lg p-4 shadow-xl">
        <p className="text-[#F5F0E8] font-medium mb-2">{d.model}</p>
        <div className="space-y-1 text-[12px] font-mono">
          <p className="text-[#C8C2B8]">Overall: <span className="text-[#F5F0E8]">{(d.overallScore * 100).toFixed(1)}</span></p>
          <p className="text-[#C8C2B8]">95% CI: <span className="text-[#F5F0E8]">{ci}</span></p>
          <p className="text-[#C8C2B8]">Latency p50: <span className="text-[#F5F0E8]">{Math.round(d.latencyP50Ms)}ms</span></p>
          <p className="text-[#C8C2B8]">Latency p95: <span className="text-[#F5F0E8]">{Math.round(d.latencyP95Ms)}ms</span></p>
          <p className="text-[#C8C2B8]">Prompts: <span className="text-[#F5F0E8]">{d.nPrompts}</span></p>
        </div>
      </div>
    );
  }
  return null;
};

export function PerformanceLatencyScatter() {
  const [data, setData] = useState<ModelPerformance[]>([]);

  useEffect(() => {
    loadLeaderboard().then(setData);
  }, []);

  if (!data.length) return null;

  const colors = buildModelColors(data.map((d) => d.model));

  const scatterData: ScatterRow[] = data.map((d) => ({
    ...d,
    ciErr: [
      d.overallScore - (d.ciLow ?? d.overallScore),
      (d.ciHigh ?? d.overallScore) - d.overallScore,
    ],
    latErr: [0, Math.max(0, d.latencyP95Ms - d.latencyP50Ms)],
  }));

  return (
    <div className="relative w-full max-w-5xl mx-auto bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-4 sm:p-6 md:p-8 border border-white/[0.06] shadow-2xl min-h-[520px]">
      <h3 className="text-[#F5F0E8] text-[18px] sm:text-[20px] font-display mb-1">Performance vs Latency</h3>
      <p className="text-[11px] text-[#C8C2B8]/70 mb-4 sm:mb-6">
        Error bars show 95% bootstrap CI (vertical) and p50–p95 latency spread (horizontal). Dot size ∝ prompts answered.
      </p>
      <div className="hidden md:flex absolute top-4 right-4 z-10 bg-[rgba(10,8,6,0.85)] backdrop-blur-md border border-white/[0.08] rounded-lg px-3 py-2.5 min-w-[160px] pointer-events-none flex-col">
        <div className="text-[10px] uppercase tracking-[0.12em] text-[#F5F0E8] mb-2">Models</div>
        <ul className="space-y-1.5">
          {data.map((d) => (
            <li key={d.model} className="flex items-center gap-2 text-[11px] text-[#C8C2B8]">
              <span className="inline-block w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: colors.get(d.model) ?? "#C8873A" }} />
              <span className="truncate" title={d.model}>{modelDisplayName(d.model)}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="w-full h-[360px] sm:h-[420px] relative">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 20, right: 40, bottom: 30, left: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis
              type="number"
              dataKey="latencyP50Ms"
              name="Latency"
              domain={["dataMin - 1000", "dataMax + 10000"]}
              tick={{ fill: "#F5F0E8", fontSize: 11 }}
              axisLine={{ stroke: "rgba(255,255,255,0.15)" }}
              tickFormatter={(v) => `${Math.round(v / 1000)}s`}
            >
              <Label value="Median Latency (seconds)" offset={-18} position="insideBottom" fill="#C8C2B8" fontSize={11} />
            </XAxis>
            <YAxis
              type="number"
              dataKey="overallScore"
              name="Overall"
              domain={[(dataMin: number) => Math.max(0, dataMin - 0.05), (dataMax: number) => Math.min(1, dataMax + 0.03)]}
              tick={{ fill: "#F5F0E8", fontSize: 11 }}
              axisLine={{ stroke: "rgba(255,255,255,0.15)" }}
              tickFormatter={(v) => (v * 100).toFixed(0)}
            >
              <Label value="Overall Score" angle={-90} position="insideLeft" fill="#C8C2B8" fontSize={11} />
            </YAxis>
            <ZAxis type="number" dataKey="nPrompts" range={[120, 380]} />
            <Tooltip content={<CustomTooltip />} cursor={{ strokeDasharray: "3 3", stroke: "rgba(255,255,255,0.15)" }} />
            <Scatter data={scatterData}>
              {scatterData.map((entry) => (
                <Cell key={entry.model} fill={colors.get(entry.model) ?? "#C8873A"} />
              ))}
              <ErrorBar dataKey="ciErr" direction="y" width={4} stroke="#F5F0E8" strokeOpacity={0.45} />
              <ErrorBar dataKey="latErr" direction="x" width={4} stroke="#F5F0E8" strokeOpacity={0.35} />
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      {/* Mobile-only inline legend */}
      <div className="md:hidden mt-4 flex flex-wrap gap-x-4 gap-y-2 justify-center">
        {data.map((d) => (
          <div key={d.model} className="flex items-center gap-2 text-[11px] text-[#C8C2B8]">
            <span className="inline-block w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: colors.get(d.model) ?? "#C8873A" }} />
            <span className="truncate max-w-[180px]" title={d.model}>{modelDisplayName(d.model)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
