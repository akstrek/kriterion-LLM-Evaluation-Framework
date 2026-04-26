import { motion } from "motion/react";
import { GrainOverlay } from "../layout/GrainOverlay";
import { BottomLeft } from "../layout/BottomLeft";
import { BottomRight } from "../layout/BottomRight";

export function Overview() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="absolute inset-0 z-10 pointer-events-none"
    >
      <GrainOverlay />
      
      <BottomLeft title="Kriterion" isOverview={true} />
      
      <div className="pointer-events-auto">
        <BottomRight 
          text="200 prompts. 3 competitors. 1 ruthless judge. Here is who won."
          ctaText="Explore Blog"
          ctaLink="/blog"
          isOverview={true}
        />
      </div>
    </motion.div>
  );
}
