import { useEffect, useRef, useState, RefObject } from "react";
import { ChevronUp } from "lucide-react";

interface ScrollToTopProps {
  scrollRef: RefObject<HTMLDivElement | null>;
  threshold?: number;
}

export function ScrollToTop({ scrollRef, threshold = 200 }: ScrollToTopProps) {
  const [visible, setVisible] = useState(false);
  const tickingRef = useRef(false);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const update = () => setVisible(el.scrollTop > threshold);

    const handleScroll = () => {
      if (tickingRef.current) return;
      tickingRef.current = true;
      requestAnimationFrame(() => {
        update();
        tickingRef.current = false;
      });
    };

    update();
    el.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      el.removeEventListener("scroll", handleScroll);
      window.removeEventListener("resize", update);
    };
  }, [scrollRef, threshold]);

  if (!visible) return null;

  return (
    <button
      type="button"
      aria-label="Scroll to top"
      onClick={() => scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" })}
      className="pointer-events-auto fixed bottom-4 left-4 z-40 md:hidden w-11 h-11 rounded-full bg-[rgba(10,8,6,0.85)] backdrop-blur-md border border-white/[0.1] shadow-2xl flex items-center justify-center text-[#F5F0E8] hover:bg-[rgba(10,8,6,0.95)] active:scale-95 transition-all"
    >
      <ChevronUp className="w-5 h-5" />
    </button>
  );
}
