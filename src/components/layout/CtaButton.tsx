import { ReactNode } from "react";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { cn } from "../../lib/utils";

interface CtaButtonProps {
  to: string;
  children: ReactNode;
  className?: string;
}

export function CtaButton({ to, children, className }: CtaButtonProps) {
  return (
    <Link
      to={to}
      className={cn(
        "group flex items-center justify-between gap-4 w-fit bg-[#F5F0E8] hover:scale-[1.03] transition-transform rounded-full p-[6px] pl-5 shadow-[0_8px_16px_rgba(200,135,58,0.1)] no-underline",
        className
      )}
    >
      <span className="text-[#0F0D0B] text-sm font-semibold">{children}</span>
      <div className="w-8 h-8 rounded-full bg-[#0F0D0B] flex items-center justify-center">
        <ArrowRight className="h-3.5 w-3.5 text-[#F5F0E8]" strokeWidth={2.5} />
      </div>
    </Link>
  );
}

