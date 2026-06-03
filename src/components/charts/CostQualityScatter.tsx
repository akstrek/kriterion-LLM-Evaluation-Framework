// DEPRECATED — no consumers. Free-tier eval makes cost axis meaningless. Pending removal or repurpose.
// @ts-nocheck
import { useEffect, useState } from 'react';
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LabelList, Cell, Label } from 'recharts';
import { loadLeaderboard } from '../../lib/loadCsv';
import { ModelPerformance } from '../../types';

const COLORS = ['#C8873A', '#4A5568', '#F5F0E8'];

const CustomTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload as ModelPerformance;
    return (
      <div className="bg-[rgba(10,8,6,0.9)] backdrop-blur-md border border-white/10 rounded-lg p-4 shadow-xl">
        <p className="text-[#F5F0E8] font-medium mb-2">{data.model}</p>
        <div className="space-y-1 text-sm">
          <p className="text-[#C8C2B8]">Score: <span className="text-[#F5F0E8]">{(data.overallScore * 100).toFixed(1)}</span></p>
          <p className="text-[#C8C2B8]">Cost: <span className="text-[#F5F0E8]">${data.costPerPrompt.toFixed(3)}</span></p>
          <p className="text-[#C8C2B8]">Latency: <span className="text-[#F5F0E8]">{data.latencyP50}s</span></p>
        </div>
      </div>
    );
  }
  return null;
};

export function CostQualityScatter() {
  const [data, setData] = useState<ModelPerformance[]>([]);

  useEffect(() => {
    loadLeaderboard().then(setData);
  }, []);

  if (!data.length) return null;

  return (
    <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-8 border border-white/[0.06] shadow-2xl min-h-[500px]">
      <h3 className="text-[#F5F0E8] text-[20px] font-display mb-8">Performance vs Cost</h3>
      <div className="w-full h-[400px]">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 20, right: 30, bottom: 20, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis 
              type="number" 
              dataKey="costPerPrompt" 
              name="Cost per Prompt" 
              domain={[0, 'auto']}
              tick={{ fill: '#F5F0E8', fontSize: 11 }}
              axisLine={{ stroke: 'rgba(255,255,255,0.15)' }}
            >
              <Label value="Cost per Prompt (USD)" offset={-10} position="insideBottom" fill="#F5F0E8" fontSize={11} />
            </XAxis>
            <YAxis 
              type="number" 
              dataKey="overallScore" 
              name="Overall Score" 
              domain={[0.7, 1]}
              tick={{ fill: '#F5F0E8', fontSize: 11 }}
              axisLine={{ stroke: 'rgba(255,255,255,0.15)' }}
              tickFormatter={(v) => (v * 100).toFixed(0)}
            >
              <Label value="Overall Score" angle={-90} position="insideLeft" fill="#F5F0E8" fontSize={11} />
            </YAxis>
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.05)' }} />
            <Scatter name="Models" data={data}>
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
              <LabelList 
                dataKey="model" 
                position="top" 
                offset={15} 
                fill="#F5F0E8" 
                fontSize={12} 
                style={{ pointerEvents: 'none' }}
              />
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
