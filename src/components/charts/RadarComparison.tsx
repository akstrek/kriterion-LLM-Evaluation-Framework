import { useEffect, useState } from 'react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Legend } from 'recharts';
import { loadEvalResults } from '../../lib/loadCsv';
import { ModelPerformance } from '../../types';

const COLORS = ['#C8873A', '#4A5568', '#F5F0E8'];

export function RadarComparison() {
  const [data, setData] = useState<ModelPerformance[]>([]);

  useEffect(() => {
    loadEvalResults().then(setData);
  }, []);

  if (!data.length) return null;

  // Format data for Radar validation
  const dimensions = [
    { key: 'factuality', label: 'Factuality' },
    { key: 'reasoning', label: 'Reasoning' },
    { key: 'instructionFollowing', label: 'Instruct' },
    { key: 'formatCompliance', label: 'Format' }
  ];

  const radarData = dimensions.map(d => {
    const row: any = { subject: d.label };
    data.forEach(modelData => {
      row[modelData.model] = (modelData as any)[d.key] * 100;
    });
    return row;
  });

  return (
    <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-8 border border-white/[0.06] shadow-2xl min-h-[400px] flex flex-col">
      <h3 className="text-[#F5F0E8] text-[16px] font-display mb-2">Model Fingerprints</h3>
      <div className="flex-1 w-full min-h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart cx="50%" cy="50%" outerRadius="80%" data={radarData}>
            <PolarGrid stroke="rgba(255,255,255,0.08)" />
            <PolarAngleAxis dataKey="subject" tick={{ fill: '#F5F0E8', fontSize: 11 }} />
            <PolarRadiusAxis angle={30} domain={[60, 100]} tick={false} axisLine={false} />
            {data.map((modelData, i) => (
              <Radar
                key={modelData.model}
                name={modelData.model}
                dataKey={modelData.model}
                stroke={COLORS[i % COLORS.length]}
                fill={COLORS[i % COLORS.length]}
                fillOpacity={0.4}
              />
            ))}
            <Legend 
              wrapperStyle={{ fontSize: '12px', color: '#F5F0E8' }} 
              iconType="circle"
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
