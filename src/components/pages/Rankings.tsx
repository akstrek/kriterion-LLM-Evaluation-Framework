import { motion } from "motion/react";
import { BottomLeft } from "../layout/BottomLeft";
import { BottomRight } from "../layout/BottomRight";
import { ScrollableZone } from "../layout/ScrollableZone";
import { LeaderboardTable } from "../charts/LeaderboardTable";
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
        <ExpandableViz>
          <LeaderboardTable />
        </ExpandableViz>
      </ScrollableZone>

      <div className="pointer-events-auto">
        <BottomRight 
          text="Model performance across all dimensions. Cost efficiency and latency at a glance."
          ctaText="Deep Dive"
          ctaLink="/dimensions"
        />
      </div>
    </motion.div>
  );
}
