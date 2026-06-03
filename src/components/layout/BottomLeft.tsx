import { cn } from "../../lib/utils";

interface BottomLeftProps {
  title: string;
  isOverview?: boolean;
}

export function BottomLeft({ title, isOverview = false }: BottomLeftProps) {
  return (
    <div
      className={cn(
        "fixed z-10 pointer-events-none",
        isOverview
          ? "bottom-6 left-5 md:bottom-8 md:left-8"
          : "hidden md:block bottom-4 left-5 md:left-6"
      )}
    >
      <h1 
        className={cn(
          "font-display text-[#F5F0E8] font-black leading-none tracking-[-0.04em] m-0",
          isOverview ? "text-[12vw] xl:text-[16vw] opacity-100" : "text-[3vw] lg:text-[4vw] opacity-50"
        )}
      >
        {title}
      </h1>
    </div>
  );
}
