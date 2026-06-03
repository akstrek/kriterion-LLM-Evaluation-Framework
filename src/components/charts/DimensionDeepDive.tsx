import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Cell, LabelList, Tooltip } from 'recharts';
import { loadEvalResults, loadDimensions } from '../../lib/loadCsv';
import { ModelPerformance } from '../../types';
import { buildModelColors, modelDisplayName } from '../../lib/modelColors';
import { useIsMobile } from '../../lib/useIsMobile';

const DimTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const p = payload[0].payload;
    return (
      <div className="bg-[rgba(10,8,6,0.92)] backdrop-blur-md border border-white/10 rounded-lg px-3 py-2 shadow-xl">
        <p className="text-[#F5F0E8] text-[12px] font-medium">{p.fullModel}</p>
        <p className="text-[#C8C2B8] text-[11px] font-mono">{p.score.toFixed(1)}</p>
      </div>
    );
  }
  return null;
};

export function DimensionDeepDive() {
  const [data, setData] = useState<ModelPerformance[]>([]);
  const [dimensions, setDimensions] = useState<string[]>([]);
  const [selectedDimension, setSelectedDimension] = useState<string>("Factuality");
  const isMobile = useIsMobile();

  useEffect(() => {
    loadEvalResults().then(setData);
    loadDimensions().then((dims) => {
      setDimensions(dims);
      if (dims.length) setSelectedDimension(dims[0]);
    });
  }, []);

  if (!data.length) return null;

  const colors = buildModelColors(data.map((d) => d.model));

  const keyMap: Record<string, keyof ModelPerformance> = {
    "Factuality": "factuality",
    "Reasoning": "reasoning",
    "Instruction Following": "instructionFollowing",
    "Format Compliance": "formatCompliance",
    "Verbosity": "verbosity"
  };

  const currentKey = keyMap[selectedDimension];
  const barData = data
    .map((d) => ({
      name: modelDisplayName(d.model),
      fullModel: d.model,
      score: (d[currentKey] as number) * 100,
    }))
    .sort((a, b) => b.score - a.score);

  return (
    <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-4 sm:p-6 md:p-8 border border-white/[0.06] shadow-2xl">
      <div className="flex justify-between items-center mb-6">
        <h3 className="text-[#F5F0E8] text-[16px] font-display">Deep Dive</h3>
        <select
          className="bg-[rgba(10,8,6,0.9)] text-[#F5F0E8] border border-white/10 rounded-md px-3 py-1.5 text-sm appearance-none outline-none focus:border-white/30"
          value={selectedDimension}
          onChange={(e) => setSelectedDimension(e.target.value)}
        >
          {dimensions.map(d => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>

      <div className="w-full h-[320px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart layout="vertical" data={barData} margin={{ top: 8, right: 56, left: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="rgba(255,255,255,0.06)" />
            <XAxis type="number" domain={[0, 100]} stroke="#C8C2B8" fontSize={11} tickLine={false} axisLine={false} />
            <YAxis
              type="category"
              dataKey="name"
              stroke="#F5F0E8"
              fontSize={isMobile ? 10 : 11}
              width={isMobile ? 96 : 180}
              tickLine={false}
              axisLine={false}
              interval={0}
            />
            <Tooltip content={<DimTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
            <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={18}>
              {barData.map((entry) => (
                <Cell key={entry.fullModel} fill={colors.get(entry.fullModel) ?? '#C8873A'} />
              ))}
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
    </div>
  );
}
