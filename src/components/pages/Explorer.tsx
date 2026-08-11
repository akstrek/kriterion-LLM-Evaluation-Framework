import { Fragment, useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { BottomLeft } from "../layout/BottomLeft";
import { BottomRight } from "../layout/BottomRight";
import { ScrollableZone } from "../layout/ScrollableZone";
import { loadResultsByPrompt } from "../../lib/loadCsv";
import { PromptResultRow } from "../../types";
import { buildModelColors, modelDisplayName } from "../../lib/modelColors";
import promptSuite from "../../../prompts/prompt_suite.json";

type SuitePrompt = {
  id: string;
  category: string;
  prompt_text: string;
  difficulty: string;
  ground_truth?: string;
};

const promptById = new Map<string, SuitePrompt>(
  (promptSuite as SuitePrompt[]).map((p) => [p.id, p])
);

const DIFFICULTIES = ["easy", "medium", "hard", "expert"];

const DIM_COLUMNS: { key: keyof PromptResultRow; label: string }[] = [
  { key: "factuality", label: "Factuality" },
  { key: "reasoning", label: "Reasoning" },
  { key: "instructionFollowing", label: "Instruct" },
  { key: "formatCompliance", label: "Format" },
  { key: "verbosity", label: "Verbosity" },
];

type SortKey = "spread" | "id" | "overall";

interface PromptGroup {
  promptId: string;
  category: string;
  difficulty: string;
  overallByModel: Map<string, number | null>;
  rowsByModel: Map<string, PromptResultRow>;
  spread: number | null;
  avgOverall: number | null;
  hasJudgeIssue: boolean;
}

function buildGroups(rows: PromptResultRow[], models: string[]): PromptGroup[] {
  const byId = new Map<string, PromptResultRow[]>();
  for (const r of rows) {
    if (!byId.has(r.promptId)) byId.set(r.promptId, []);
    byId.get(r.promptId)!.push(r);
  }
  const groups: PromptGroup[] = [];
  for (const [promptId, groupRows] of byId) {
    const overallByModel = new Map<string, number | null>();
    const rowsByModel = new Map<string, PromptResultRow>();
    for (const r of groupRows) {
      overallByModel.set(r.model, r.overall);
      rowsByModel.set(r.model, r);
    }
    const nonNull = models
      .map((m) => overallByModel.get(m))
      .filter((v): v is number => v !== null && v !== undefined);
    const spread = nonNull.length >= 2 ? Math.max(...nonNull) - Math.min(...nonNull) : null;
    const avgOverall = nonNull.length
      ? nonNull.reduce((a, b) => a + b, 0) / nonNull.length
      : null;
    groups.push({
      promptId,
      category: groupRows[0].category,
      difficulty: groupRows[0].difficulty,
      overallByModel,
      rowsByModel,
      spread,
      avgOverall,
      hasJudgeIssue: groupRows.some((r) => r.judgeEmpty),
    });
  }
  return groups;
}

// Descending by value; null (fewer than 2 non-null scores to compare) always sorts last.
function compareDescNullsLast(av: number | null, bv: number | null): number {
  if (av === null && bv === null) return 0;
  if (av === null) return 1;
  if (bv === null) return -1;
  return bv - av;
}

function sortGroups(groups: PromptGroup[], sortKey: SortKey): PromptGroup[] {
  const arr = [...groups];
  if (sortKey === "id") {
    arr.sort((a, b) => a.promptId.localeCompare(b.promptId));
  } else if (sortKey === "spread") {
    arr.sort((a, b) => compareDescNullsLast(a.spread, b.spread) || a.promptId.localeCompare(b.promptId));
  } else {
    arr.sort((a, b) => compareDescNullsLast(a.avgOverall, b.avgOverall) || a.promptId.localeCompare(b.promptId));
  }
  return arr;
}

const fmtScore = (v: number | null) => (v === null ? "—" : (v * 100).toFixed(1));

const selectClass =
  "bg-[rgba(10,8,6,0.9)] text-[#F5F0E8] border border-white/10 rounded-md px-3 py-1.5 text-[12px] appearance-none outline-none focus:border-white/30";

const chipClass =
  "inline-block px-2 py-0.5 rounded-md bg-white/[0.06] border border-white/[0.08] text-[#C8C2B8] text-[10px] tracking-wide font-mono whitespace-nowrap";

const PAGE_SIZE = 50;

export function Explorer() {
  const [data, setData] = useState<PromptResultRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState("All");
  const [difficultyFilter, setDifficultyFilter] = useState("All");
  const [judgeIssuesOnly, setJudgeIssuesOnly] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("spread");
  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadResultsByPrompt().then((rows) => {
      setData(rows);
      setLoaded(true);
    });
  }, []);

  const models = useMemo(
    () => Array.from(new Set(data.map((r) => r.model))).sort(),
    [data]
  );
  const colors = useMemo(() => buildModelColors(models), [models]);

  const groups = useMemo(() => buildGroups(data, models), [data, models]);

  const categories = useMemo(
    () => Array.from(new Set(groups.map((g) => g.category))).sort(),
    [groups]
  );

  const filtered = useMemo(() => {
    return groups.filter(
      (g) =>
        (categoryFilter === "All" || g.category === categoryFilter) &&
        (difficultyFilter === "All" || g.difficulty === difficultyFilter) &&
        (!judgeIssuesOnly || g.hasJudgeIssue)
    );
  }, [groups, categoryFilter, difficultyFilter, judgeIssuesOnly]);

  const sorted = useMemo(() => sortGroups(filtered, sortKey), [filtered, sortKey]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const clampedPage = Math.min(page, totalPages - 1);
  const pageRows = sorted.slice(clampedPage * PAGE_SIZE, clampedPage * PAGE_SIZE + PAGE_SIZE);

  const resetPage = () => setPage(0);

  const toggle = (promptId: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(promptId)) next.delete(promptId);
      else next.add(promptId);
      return next;
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="absolute inset-0 z-10 pointer-events-none"
    >
      <BottomLeft title="Explorer" />

      <ScrollableZone>
        <div className="w-full pointer-events-auto space-y-6">
          {!loaded ? null : !data.length ? (
            <div className="w-full max-w-5xl mx-auto bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-6 md:p-8 border border-white/[0.06] shadow-2xl">
              <p className="text-[#C8C2B8] text-[13px] leading-relaxed">
                The per-prompt export hasn't been generated yet. Run{" "}
                <code className="text-[#F5F0E8] font-mono">leaderboard.py</code> after an eval
                run to populate <code className="text-[#F5F0E8] font-mono">results_by_prompt.csv</code>.
              </p>
            </div>
          ) : (
            <div className="w-full max-w-5xl mx-auto bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-4 sm:p-6 md:p-8 border border-white/[0.06] shadow-2xl overflow-x-auto">
              <div className="flex flex-wrap items-center gap-3 mb-5">
                <select
                  className={selectClass}
                  value={categoryFilter}
                  onChange={(e) => {
                    setCategoryFilter(e.target.value);
                    resetPage();
                  }}
                >
                  <option value="All">All categories</option>
                  {categories.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>

                <select
                  className={selectClass}
                  value={difficultyFilter}
                  onChange={(e) => {
                    setDifficultyFilter(e.target.value);
                    resetPage();
                  }}
                >
                  <option value="All">All difficulties</option>
                  {DIFFICULTIES.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>

                <select
                  className={selectClass}
                  value={sortKey}
                  onChange={(e) => {
                    setSortKey(e.target.value as SortKey);
                    resetPage();
                  }}
                >
                  <option value="spread">Sort: Spread ↓</option>
                  <option value="overall">Sort: Overall ↓</option>
                  <option value="id">Sort: Prompt ID</option>
                </select>

                <label className="flex items-center gap-2 text-[12px] text-[#C8C2B8] cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={judgeIssuesOnly}
                    onChange={(e) => {
                      setJudgeIssuesOnly(e.target.checked);
                      resetPage();
                    }}
                    className="accent-[#C8873A]"
                  />
                  Judge issues only
                </label>

                <span className="text-[11px] text-[#C8C2B8]/60 ml-auto">
                  {sorted.length} prompts
                </span>
              </div>

              <table className="w-full text-left border-collapse min-w-[420px] md:min-w-[820px]">
                <thead className="border-b border-white/[0.1]">
                  <tr className="text-[#F5F0E8] text-[10px] uppercase tracking-[0.12em]">
                    <th className="pb-3 pr-2 font-semibold w-8"></th>
                    <th className="pb-3 pr-2 font-semibold">Prompt</th>
                    <th className="pb-3 pr-2 font-semibold hidden sm:table-cell">Category</th>
                    <th className="pb-3 pr-2 font-semibold hidden sm:table-cell">Difficulty</th>
                    {models.map((m) => (
                      <th
                        key={m}
                        className="pb-3 px-3 font-semibold text-right hidden sm:table-cell"
                        title={m}
                      >
                        {modelDisplayName(m)}
                      </th>
                    ))}
                    <th className="pb-3 pl-3 font-semibold text-right">Spread</th>
                  </tr>
                </thead>
                <tbody className="text-[#C8C2B8] text-[13px]">
                  {pageRows.map((g) => {
                    const isOpen = expanded.has(g.promptId);
                    const suite = promptById.get(g.promptId);
                    return (
                      <Fragment key={g.promptId}>
                        <tr
                          className="hover:bg-white/[0.03] transition-colors cursor-pointer border-b border-white/[0.04]"
                          onClick={() => toggle(g.promptId)}
                        >
                          <td className="py-3 pr-2 text-[#C8C2B8] select-none">
                            <span className={`inline-block transition-transform ${isOpen ? "rotate-90" : ""}`}>
                              ›
                            </span>
                          </td>
                          <td className="py-3 pr-2 text-[#F5F0E8] font-mono text-[12px]">{g.promptId}</td>
                          <td className="py-3 pr-2 hidden sm:table-cell">
                            <span className={chipClass}>{g.category}</span>
                          </td>
                          <td className="py-3 pr-2 hidden sm:table-cell">
                            <span className={chipClass}>{g.difficulty}</span>
                          </td>
                          {models.map((m) => (
                            <td key={m} className="py-3 px-3 text-right font-mono hidden sm:table-cell">
                              {fmtScore(g.overallByModel.get(m) ?? null)}
                            </td>
                          ))}
                          <td className="py-3 pl-3 text-right font-mono text-[#C8873A]">
                            {g.spread === null ? "—" : (g.spread * 100).toFixed(1)}
                          </td>
                        </tr>
                        {isOpen && (
                          <tr className="bg-white/[0.02]">
                            <td colSpan={5 + models.length} className="py-5 px-4">
                              <div className="space-y-4">
                                {suite?.prompt_text && (
                                  <div>
                                    <div className="text-[10px] uppercase tracking-[0.12em] text-[#F5F0E8] mb-1">
                                      Prompt
                                    </div>
                                    <p className="text-[12px] text-[#C8C2B8] leading-relaxed max-w-3xl">
                                      {suite.prompt_text}
                                    </p>
                                  </div>
                                )}
                                {suite?.ground_truth && (
                                  <div>
                                    <div className="text-[10px] uppercase tracking-[0.12em] text-[#F5F0E8] mb-1">
                                      Ground Truth
                                    </div>
                                    <p className="text-[12px] text-[#C8C2B8] leading-relaxed max-w-3xl font-mono">
                                      {suite.ground_truth}
                                    </p>
                                  </div>
                                )}
                                <div>
                                  <div className="text-[10px] uppercase tracking-[0.12em] text-[#F5F0E8] mb-2">
                                    Scores
                                  </div>
                                  <div className="overflow-x-auto">
                                    <table className="text-[12px] border-collapse">
                                      <thead>
                                        <tr className="text-[#F5F0E8] text-[10px] uppercase tracking-[0.1em]">
                                          <th className="pb-2 pr-4 text-left font-semibold">Model</th>
                                          {DIM_COLUMNS.map((d) => (
                                            <th key={d.key} className="pb-2 px-3 text-right font-semibold">
                                              {d.label}
                                            </th>
                                          ))}
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {models.map((m) => {
                                          const row = g.rowsByModel.get(m);
                                          return (
                                            <tr key={m}>
                                              <td className="py-1.5 pr-4 font-medium" style={{ color: colors.get(m) }}>
                                                {modelDisplayName(m)}
                                              </td>
                                              {DIM_COLUMNS.map((d) => (
                                                <td key={d.key} className="py-1.5 px-3 text-right font-mono">
                                                  {row ? fmtScore(row[d.key] as number | null) : "—"}
                                                </td>
                                              ))}
                                            </tr>
                                          );
                                        })}
                                      </tbody>
                                    </table>
                                  </div>
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

              <div className="flex items-center justify-between mt-5 pt-4 border-t border-white/[0.06]">
                <button
                  type="button"
                  disabled={clampedPage === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  className="text-[11px] uppercase tracking-[0.1em] text-[#C8C2B8] hover:text-[#F5F0E8] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  ← Prev
                </button>
                <span className="text-[11px] text-[#C8C2B8]/70 font-mono">
                  Page {clampedPage + 1} / {totalPages}
                </span>
                <button
                  type="button"
                  disabled={clampedPage >= totalPages - 1}
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  className="text-[11px] uppercase tracking-[0.1em] text-[#C8C2B8] hover:text-[#F5F0E8] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </div>
      </ScrollableZone>

      <div className="pointer-events-auto">
        <BottomRight
          text="Per-prompt scores across all three models — sorted by disagreement by default."
          ctaText="View Rankings"
          ctaLink="/rankings"
        />
      </div>
    </motion.div>
  );
}
