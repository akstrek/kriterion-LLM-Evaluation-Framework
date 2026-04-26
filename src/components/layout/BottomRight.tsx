import { CtaButton } from "./CtaButton";
import { cn } from "../../lib/utils";

interface BottomRightProps {
  text: string;
  ctaText?: string;
  ctaLink?: string;
  isOverview?: boolean;
}

export function BottomRight({ text, ctaText, ctaLink, isOverview = false }: BottomRightProps) {
  return (
    <div className={cn(
      "fixed z-10 pointer-events-auto",
      isOverview
        ? "bottom-6 right-5 md:bottom-8 md:right-8 flex flex-col items-end gap-3"
        : "bottom-4 right-5 md:right-6 flex flex-row items-center gap-4 md:gap-6"
    )}>
      <p className={cn(
        "m-0 text-right",
        isOverview
          ? "font-display font-black tracking-[-0.04em] leading-tight text-black text-[6vw] md:text-[3vw] xl:text-[2.8vw] max-w-[55vw] md:max-w-[42vw]"
          : "font-sans leading-relaxed text-[#C8C2B8] text-[11px] md:text-[12px] max-w-[350px]"
      )}>
        {text}
      </p>
      {ctaText && ctaLink && (
        <CtaButton to={ctaLink}>{ctaText}</CtaButton>
      )}
    </div>
  );
}
