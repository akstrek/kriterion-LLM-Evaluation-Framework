import { ReactNode, useRef } from "react";
import { cn } from "../../lib/utils";
import { ScrollToTop } from "./ScrollToTop";

interface ScrollableZoneProps {
  children: ReactNode;
  className?: string;
}

export function ScrollableZone({ children, className }: ScrollableZoneProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  return (
    <div className="fixed inset-0 top-[60px] pb-[56px] z-[5] pointer-events-none flex items-center justify-center">
      <div
        ref={scrollRef}
        className={cn(
          "w-[92%] sm:w-[90%] lg:w-[80%] max-h-full overflow-y-auto pointer-events-auto",
          className
        )}
      >
        <div className="py-6 md:py-12 min-h-full flex flex-col justify-center">
          {children}
        </div>
      </div>
      <ScrollToTop scrollRef={scrollRef} />
    </div>
  );
}
