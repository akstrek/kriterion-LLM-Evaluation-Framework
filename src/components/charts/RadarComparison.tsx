import { useEffect, useState } from 'react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Legend } from 'recharts';
import { loadEvalResults } from '../../lib/loadCsv';
import { ModelPerformance } from '../../types';
import { buildModelColors, modelDisplayName } from '../../lib/modelColors';
import { useIsMobile } from '../../lib/useIsMobile';

export function RadarComparison() {
  const [data, setData] = useState<ModelPerformance[]>([]);
  const isMobile = useIsMobile();

  useEffect(() => {
    loadEvalResults().then(setData);
  }, []);

  if (!data.length) return null;

  const colors = buildModelColors(data.map((d) => d.model));

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
    <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-4 sm:p-6 md:p-8 border border-white/[0.06] shadow-2xl">
      <h3 className="text-[#F5F0E8] text-[16px] font-display mb-2">Model Fingerprints</h3>
      <div className="w-full h-[320px] sm:h-[340px]">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart cx="50%" cy="50%" outerRadius={isMobile ? '68%' : '80%'} data={radarData}>
            <PolarGrid stroke="rgba(255,255,255,0.08)" />
            <PolarAngleAxis dataKey="subject" tick={{ fill: '#F5F0E8', fontSize: isMobile ? 10 : 11 }} />
            <PolarRadiusAxis angle={30} domain={[60, 100]} tick={false} axisLine={false} />
            {data.map((modelData) => {
              const color = colors.get(modelData.model) ?? '#C8873A';
              return (
                <Radar
                  key={modelData.model}
                  name={modelDisplayName(modelData.model)}
                  dataKey={modelData.model}
                  stroke={color}
                  fill={color}
                  fillOpacity={0.35}
                />
              );
            })}
            <Legend
              wrapperStyle={{ fontSize: isMobile ? '10px' : '12px', color: '#F5F0E8', paddingTop: 8 }}
              iconType="circle"
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
