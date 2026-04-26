import { motion } from "motion/react";
import { BottomLeft } from "../layout/BottomLeft";
import { BottomRight } from "../layout/BottomRight";
import { ScrollableZone } from "../layout/ScrollableZone";
import { ExpandableViz } from "../layout/ExpandableViz";

export function Methods() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="absolute inset-0 z-10 pointer-events-none"
    >
      <BottomLeft title="Methods" />
      
      <ScrollableZone>
        <ExpandableViz>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full pointer-events-auto">
            <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-8 border border-white/[0.06] shadow-2xl">
              <h3 className="text-[#F5F0E8] font-display text-[16px] mb-4">Evaluation Dimensions</h3>
            <div className="space-y-4">
              <div>
                <p className="text-[#F5F0E8] text-[13px] uppercase tracking-wider mb-1">Factuality</p>
                <p className="text-[#C8C2B8] text-[12px]">Accuracy of claims measured against ground knowledge.</p>
              </div>
              <div>
                <p className="text-[#F5F0E8] text-[13px] uppercase tracking-wider mb-1">Reasoning</p>
                <p className="text-[#C8C2B8] text-[12px]">Multi-step logical deduction and synthesis capability.</p>
              </div>
              <div>
                <p className="text-[#F5F0E8] text-[13px] uppercase tracking-wider mb-1">Instruction Following</p>
                <p className="text-[#C8C2B8] text-[12px]">Adherence to complex, multi-constraint system prompts.</p>
              </div>
              <div>
                <p className="text-[#F5F0E8] text-[13px] uppercase tracking-wider mb-1">Format Compliance</p>
                <p className="text-[#C8C2B8] text-[12px]">Strict output syntax matching (e.g. valid JSON).</p>
              </div>
            </div>
          </div>

          <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-8 border border-white/[0.06] shadow-2xl">
            <h3 className="text-[#F5F0E8] font-display text-[16px] mb-4">Scoring Approach</h3>
            <p className="text-[#C8C2B8] text-[12px] line-height-[1.6]">
              All permutations are auto-evaluated using a zero-shot scoring proxy. 
              The judge model reads the task context, the generated candidate response, and the scoring rubric to assign a [0.0 - 1.0] continuous value. <br/><br/>
              Note: Judge model: Gemini 2.0 Flash — upgrade path to Claude documented.
            </p>
          </div>

          <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-8 border border-white/[0.06] shadow-2xl">
            <h3 className="text-[#F5F0E8] font-display text-[16px] mb-4">Prompt Categories</h3>
            <div className="space-y-2">
              <div className="flex justify-between border-b border-white/10 pb-1">
                <span className="text-[#F5F0E8] text-[13px]">Creative Writing</span>
                <span className="text-[#C8C2B8] text-[13px]">40</span>
              </div>
              <div className="flex justify-between border-b border-white/10 pb-1">
                <span className="text-[#F5F0E8] text-[13px]">Coding & Logic</span>
                <span className="text-[#C8C2B8] text-[13px]">65</span>
              </div>
              <div className="flex justify-between border-b border-white/10 pb-1">
                <span className="text-[#F5F0E8] text-[13px]">Data Extraction</span>
                <span className="text-[#C8C2B8] text-[13px]">45</span>
              </div>
              <div className="flex justify-between border-b border-white/10 pb-1">
                <span className="text-[#F5F0E8] text-[13px]">Mathematics</span>
                <span className="text-[#C8C2B8] text-[13px]">30</span>
              </div>
              <div className="flex justify-between pt-1">
                <span className="text-[#F5F0E8] text-[13px] font-bold">Total</span>
                <span className="text-[#C8C2B8] text-[13px] font-bold">200</span>
              </div>
            </div>
          </div>

          <div className="bg-[rgba(10,8,6,0.72)] backdrop-blur-2xl rounded-2xl p-8 border border-white/[0.06] shadow-2xl">
            <h3 className="text-[#F5F0E8] font-display text-[16px] mb-4">Known Limitations</h3>
            <ul className="list-disc pl-4 space-y-2 text-[#C8C2B8] text-[12px] marker:text-[#F5F0E8]">
              <li>Judge bias towards its own family models or specific stylistic patterns.</li>
              <li>Prompt selection bias leaning towards coding and formal logic.</li>
              <li>Lack of human validation across the current 200 prompt split.</li>
            </ul>
          </div>
          </div>
        </ExpandableViz>
      </ScrollableZone>

      <div className="pointer-events-auto">
        <BottomRight text="How we scored 200 prompts across 3 models without human labels." />
      </div>
    </motion.div>
  );
}
