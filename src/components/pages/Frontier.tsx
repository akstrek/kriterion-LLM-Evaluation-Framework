import { motion } from "motion/react";
import { BottomLeft } from "../layout/BottomLeft";
import { BottomRight } from "../layout/BottomRight";
import { ScrollableZone } from "../layout/ScrollableZone";
import { CostQualityScatter } from "../charts/CostQualityScatter";
import { ExpandableViz } from "../layout/ExpandableViz";

export function Frontier() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="absolute inset-0 z-10 pointer-events-none"
    >
      <BottomLeft title="Frontier" />
      
      <ScrollableZone>
        <div className="w-full pointer-events-auto">
          <ExpandableViz>
            <CostQualityScatter />
          </ExpandableViz>
        </div>
      </ScrollableZone>

      <div className="pointer-events-auto">
        <BottomRight 
          text="Cost efficiency vs output quality. Where each model sits on the performance curve."
          ctaText="Read Methods"
          ctaLink="/methods"
        />
      </div>
    </motion.div>
  );
}
