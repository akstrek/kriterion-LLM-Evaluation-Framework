import { useEffect, useState } from "react";
import { loadLeaderboard } from "../../lib/loadCsv";
import { ModelPerformance } from "../../types";

export function LeaderboardTable() {
  const [data, setData] = useState<ModelPerformance[]>([]);

  useEffect(() => {
    loadLeaderboard().then(setData);
  }, []);

  if (!data.length) return null;

  // Find best values for highlighting
  const bestFactuality = Math.max(...data.map(d => d.factuality));
  const bestReasoning = Math.max(...data.map(d => d.reasoning));
  const bestInstruction = Math.max(...data.map(d => d.instructionFollowing));
  const bestFormat = Math.max(...data.map(d => d.formatCompliance));
  const bestCost = Math.min(...data.map(d => d.costPerPrompt));
  const bestLatency = Math.min(...data.map(d => d.latencyP50));

  return (
    <div className="w-full max-w-4xl mx-auto bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-8 border border-white/[0.06] shadow-2xl overflow-x-auto">
      <table className="w-full text-left border-collapse min-w-[800px]">
        <thead className="border-b border-white/[0.1]">
          <tr className="text-[#F5F0E8] text-[10px] uppercase tracking-[0.12em]">
            <th className="pb-4 font-semibold">Model</th>
            <th className="pb-4 font-semibold text-right">Overall</th>
            <th className="pb-4 font-semibold text-right">Factuality</th>
            <th className="pb-4 font-semibold text-right">Reasoning</th>
            <th className="pb-4 font-semibold text-right">Instruct</th>
            <th className="pb-4 font-semibold text-right">Format</th>
            <th className="pb-4 font-semibold text-right">Cost/Pt</th>
            <th className="pb-4 font-semibold text-right pl-4">Latency p50</th>
          </tr>
        </thead>
        <tbody className="text-[#C8C2B8] text-[13px]">
          {data.map((row, i) => (
            <tr 
              key={row.model} 
              className="hover:bg-white/[0.03] transition-colors"
            >
              <td className="py-4 text-[#F5F0E8] font-medium pr-4">
                {row.model}
              </td>
              <td className="py-4 px-4 text-right">
                <span className={`text-[#C8873A]`}>
                  {(row.overallScore * 100).toFixed(1)}
                </span>
              </td>
              <td className={`py-4 px-4 text-right`}>
                <span className={row.factuality === bestFactuality ? 'border-b border-[#F5F0E8] text-[#F5F0E8]' : ''}>
                  {(row.factuality * 100).toFixed(1)}
                </span>
              </td>
              <td className={`py-4 px-4 text-right`}>
                <span className={row.reasoning === bestReasoning ? 'border-b border-[#F5F0E8] text-[#F5F0E8]' : ''}>
                  {(row.reasoning * 100).toFixed(1)}
                </span>
              </td>
              <td className={`py-4 px-4 text-right`}>
                <span className={row.instructionFollowing === bestInstruction ? 'border-b border-[#F5F0E8] text-[#F5F0E8]' : ''}>
                  {(row.instructionFollowing * 100).toFixed(1)}
                </span>
              </td>
              <td className={`py-4 px-4 text-right`}>
                <span className={row.formatCompliance === bestFormat ? 'border-b border-[#F5F0E8] text-[#F5F0E8]' : ''}>
                  {(row.formatCompliance * 100).toFixed(1)}
                </span>
              </td>
              <td className={`py-4 px-4 text-right font-mono`}>
                <span className={row.costPerPrompt === bestCost ? 'border-b border-[#F5F0E8] text-[#F5F0E8]' : ''}>
                  ${row.costPerPrompt.toFixed(3)}
                </span>
              </td>
              <td className={`py-4 pr-4 pl-4 text-right font-mono`}>
                <span className={row.latencyP50 === bestLatency ? 'border-b border-[#F5F0E8] text-[#F5F0E8]' : ''}>
                  {row.latencyP50.toFixed(1)}s
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
