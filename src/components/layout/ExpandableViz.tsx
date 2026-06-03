import { ReactNode, useState, useEffect } from "react";
import { Expand, Shrink } from "lucide-react";
import { cn } from "../../lib/utils";
import { motion, AnimatePresence } from "motion/react";

interface ExpandableVizProps {
  children: ReactNode;
}

export function ExpandableViz({ children }: ExpandableVizProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Focus lock or escape key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsExpanded(false);
    };
    if (isExpanded) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isExpanded]);

  return (
    <>
      <div className="relative group w-full h-full pointer-events-auto">
        <button
          aria-label="Expand"
          onClick={() => setIsExpanded(true)}
          className="absolute top-2 right-2 md:-top-3 md:-right-3 z-[60] p-2 md:p-1.5 text-[#C8C2B8] hover:text-[#F5F0E8] hover:bg-[rgba(255,255,255,0.1)] opacity-70 md:opacity-0 md:group-hover:opacity-100 transition-all bg-[rgba(10,8,6,0.95)] rounded-md shadow-2xl border border-white/[0.1] backdrop-blur-md cursor-pointer"
        >
          <Expand className="w-5 h-5 md:w-4 md:h-4" />
        </button>
        {children}
      </div>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ opacity: 0, backdropFilter: "blur(0px)" }}
            animate={{ opacity: 1, backdropFilter: "blur(24px)" }}
            exit={{ opacity: 0, backdropFilter: "blur(0px)" }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="fixed inset-0 z-[100] bg-[rgba(10,8,6,0.90)] p-4 sm:p-6 md:p-12 lg:p-20 flex flex-col pointer-events-auto overflow-y-auto"
          >
            <button
              onClick={() => setIsExpanded(false)}
              className="fixed top-6 right-6 z-[110] p-2 text-[#C8C2B8] hover:text-white hover:bg-[rgba(255,255,255,0.1)] transition-colors bg-[rgba(10,8,6,0.8)] rounded-md shadow-lg border border-white/10 cursor-pointer"
            >
              <Shrink className="w-5 h-5" />
            </button>
            <div className="flex-1 w-full h-full min-h-[400px] sm:min-h-[500px] flex px-0 sm:px-4">
              <div className="w-full h-full max-w-7xl mx-auto relative flex flex-col items-center justify-center">
                 <div className="w-full origin-center">
                   {children}
                 </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
