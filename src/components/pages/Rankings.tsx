import { motion } from "motion/react";
import { BottomLeft } from "../layout/BottomLeft";
import { BottomRight } from "../layout/BottomRight";
import { ScrollableZone } from "../layout/ScrollableZone";
import { LeaderboardTable } from "../charts/LeaderboardTable";
import { PerformanceLatencyScatter } from "../charts/PerformanceLatencyScatter";
import { DifficultyBreakdown } from "../charts/DifficultyBreakdown";
import { ExpandableViz } from "../layout/ExpandableViz";

export function Rankings() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="absolute inset-0 z-10 pointer-events-none"
    >
      <BottomLeft title="Rankings" />

      <ScrollableZone>
        <div className="w-full pointer-events-auto space-y-6">
          <ExpandableViz>
            <LeaderboardTable />
          </ExpandableViz>
          <ExpandableViz>
            <PerformanceLatencyScatter />
          </ExpandableViz>
          <ExpandableViz>
            <DifficultyBreakdown />
          </ExpandableViz>
        </div>
      </ScrollableZone>

      <div className="pointer-events-auto">
        <BottomRight
          text="Overall scores with 95% CI, per-dimension breakdown, and latency vs quality at a glance."
          ctaText="Deep Dive"
          ctaLink="/dimensions"
        />
      </div>
    </motion.div>
  );
}
