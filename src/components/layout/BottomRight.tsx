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
        ? "top-[68px] right-4 md:top-auto md:bottom-8 md:right-8 flex flex-col items-end gap-2 md:gap-3"
        : "bottom-3 right-3 md:bottom-4 md:right-6 flex flex-col items-end gap-2 md:flex-row md:items-center md:gap-6 max-w-[calc(100vw-1.5rem)]"
    )}>
      <p className={cn(
        "m-0 text-right",
        isOverview
          ? "font-display font-black tracking-[-0.03em] leading-[1.05] text-black text-[3.4vw] md:text-[1.7vw] xl:text-[1.55vw] max-w-[55vw] md:max-w-[24vw] whitespace-pre-line"
          : "font-sans leading-snug text-[#C8C2B8] text-[10px] md:text-[12px] max-w-[200px] md:max-w-[350px]"
      )}>
        {text}
      </p>
      {ctaText && ctaLink && (
        <CtaButton to={ctaLink}>{ctaText}</CtaButton>
      )}
    </div>
  );
}
