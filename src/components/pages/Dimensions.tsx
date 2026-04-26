import { motion } from "motion/react";
import { BottomLeft } from "../layout/BottomLeft";
import { BottomRight } from "../layout/BottomRight";
import { ScrollableZone } from "../layout/ScrollableZone";
import { RadarComparison } from "../charts/RadarComparison";
import { DimensionDeepDive } from "../charts/DimensionDeepDive";
import { ExpandableViz } from "../layout/ExpandableViz";

export function Dimensions() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="absolute inset-0 z-10 pointer-events-none"
    >
      <BottomLeft title="Dimensions" />
      
      <ScrollableZone>
        {/* We have left component (Radar) and right component (Deep Dive) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 w-full pointer-events-auto">
          <ExpandableViz>
            <RadarComparison />
          </ExpandableViz>
          <ExpandableViz>
            <DimensionDeepDive />
          </ExpandableViz>
        </div>
      </ScrollableZone>

      <div className="pointer-events-auto">
        <BottomRight 
          text="How each model performs across factuality, reasoning, instruction following, and format compliance."
          ctaText="View Frontier"
          ctaLink="/frontier"
        />
      </div>
    </motion.div>
  );
}
