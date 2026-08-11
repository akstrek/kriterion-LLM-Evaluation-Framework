import { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { Menu, X } from "lucide-react";
import { cn } from "../../lib/utils";

const NAV_LINKS = [
  { name: "Overview", path: "/" },
  { name: "Rankings", path: "/rankings" },
  { name: "Dimensions", path: "/dimensions" },
  { name: "Explorer", path: "/explorer" },
  { name: "Methods", path: "/methods" },
  { name: "Blog", path: "/blog" },
];

export function Navbar() {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onClickAway = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClickAway);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("mousedown", onClickAway);
      document.removeEventListener("keydown", onEscape);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="fixed top-0 left-1/2 -translate-x-1/2 z-50 w-full md:w-auto md:max-w-[100vw]">
      {/* Desktop: horizontal pill */}
      <nav className="hidden md:flex items-center gap-8 px-8 h-[52px] bg-[rgba(10,8,6,0.72)] backdrop-blur-xl rounded-b-2xl border-x border-b border-white/[0.05]">
        {NAV_LINKS.map((link) => (
          <NavLink
            key={link.path}
            to={link.path}
            className={({ isActive }) =>
              cn(
                "text-xs tracking-wider transition-colors shrink-0",
                isActive
                  ? "text-[#F5F0E8] font-medium"
                  : "text-[#C8C2B8] hover:text-[#F5F0E8]"
              )
            }
          >
            {link.name}
          </NavLink>
        ))}
      </nav>

      {/* Mobile: hamburger only — no duplicate brand mark */}
      <div className="md:hidden flex items-center justify-end px-3 h-[52px] bg-[rgba(10,8,6,0.85)] backdrop-blur-xl border-b border-white/[0.05]">
        <button
          type="button"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          className="w-11 h-11 flex items-center justify-center text-[#F5F0E8] active:scale-95 transition-transform"
        >
          {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      <AnimatePresence>
        {open && (
          <motion.nav
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="md:hidden bg-[rgba(10,8,6,0.95)] backdrop-blur-xl border-b border-white/[0.05]"
          >
            <ul className="flex flex-col py-2">
              {NAV_LINKS.map((link) => (
                <li key={link.path}>
                  <NavLink
                    to={link.path}
                    onClick={() => setOpen(false)}
                    className={({ isActive }) =>
                      cn(
                        "block px-5 py-3 text-[13px] tracking-wider transition-colors border-l-2",
                        isActive
                          ? "text-[#F5F0E8] font-medium border-[#F5C387] bg-white/[0.04]"
                          : "text-[#C8C2B8] border-transparent hover:text-[#F5F0E8] hover:bg-white/[0.02]"
                      )
                    }
                  >
                    {link.name}
                  </NavLink>
                </li>
              ))}
            </ul>
          </motion.nav>
        )}
      </AnimatePresence>
    </div>
  );
}
