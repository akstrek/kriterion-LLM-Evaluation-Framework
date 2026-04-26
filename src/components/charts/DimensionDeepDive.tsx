import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Cell } from 'recharts';
import { loadEvalResults, loadDimensions } from '../../lib/loadCsv';
import { ModelPerformance } from '../../types';

const COLORS = ['#C8873A', '#4A5568', '#F5F0E8'];

const SAMPLE_RESPONSES: Record<string, string[]> = {
  "Claude Sonnet 4": [
    "The data strongly suggests the initial claim is unsubstantiated...",
    "Given the parameters, X = 42 based on the derivation..."
  ],
  "GPT-4o": [
    "While some sources point to A, the primary consensus is B...",
    "To solve this, we first isolate the variable returning 42..."
  ],
  "Gemini Flash 2.0": [
    "According to verified DB sources, the entity was indeed present...",
    "1. Setup equation, 2. Isolate variable, 3. X=42."
  ]
};

export function DimensionDeepDive() {
  const [data, setData] = useState<ModelPerformance[]>([]);
  const [dimensions, setDimensions] = useState<string[]>([]);
  const [selectedDimension, setSelectedDimension] = useState<string>("Factuality");

  useEffect(() => {
    loadEvalResults().then(setData);
    loadDimensions().then((dims) => {
      setDimensions(dims);
      if (dims.length) setSelectedDimension(dims[0]);
    });
  }, []);

  if (!data.length) return null;

  const keyMap: Record<string, keyof ModelPerformance> = {
    "Factuality": "factuality",
    "Reasoning": "reasoning",
    "Instruction Following": "instructionFollowing",
    "Format Compliance": "formatCompliance"
  };

  const currentKey = keyMap[selectedDimension];
  const barData = data.map(d => ({
    name: d.model,
    score: (d[currentKey] as number) * 100
  })).sort((a,b) => b.score - a.score);

  return (
    <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-8 border border-white/[0.06] shadow-2xl min-h-[400px] flex flex-col">
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

      <div className="w-full h-[180px] mb-6">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart layout="vertical" data={barData} margin={{ top: 0, right: 30, left: 10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="rgba(255,255,255,0.08)" />
            <XAxis type="number" domain={[50, 100]} stroke="#F5F0E8" fontSize={11} tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey="name" stroke="#F5F0E8" fontSize={11} width={100} tickLine={false} axisLine={false} />
            <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={20}>
              {barData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="space-y-3 mt-auto">
        <p className="text-[#F5F0E8] text-[11px] uppercase tracking-wider mb-2">Sample Completions</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {data.slice(0, 2).map((modelData, idx) => (
            <div key={modelData.model} className="bg-[rgba(10,8,6,0.4)] border border-[#F5F0E8]/10 rounded-lg p-3">
              <div className="text-[#F5F0E8] text-[11px] uppercase tracking-wider mb-2">{modelData.model}</div>
              <p className="text-[#C8C2B8] text-[12px] line-clamp-3">
                "{SAMPLE_RESPONSES[modelData.model]?.[0] || 'Generated response text goes here based on selected criteria...'}"
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
