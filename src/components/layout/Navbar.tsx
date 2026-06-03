import { NavLink } from "react-router-dom";
import { cn } from "../../lib/utils";

const NAV_LINKS = [
  { name: "Overview", path: "/" },
  { name: "Rankings", path: "/rankings" },
  { name: "Dimensions", path: "/dimensions" },
  { name: "Methods", path: "/methods" },
  { name: "Blog", path: "/blog" },
];

export function Navbar() {
  return (
    <nav className="fixed top-0 left-1/2 -translate-x-1/2 z-50 max-w-[100vw]">
      <div className="flex items-center gap-4 md:gap-8 px-5 md:px-8 h-[52px] bg-[rgba(10,8,6,0.72)] backdrop-blur-xl rounded-b-2xl border-x border-b border-white/[0.05] overflow-x-auto [&::-webkit-scrollbar]:hidden">
        {NAV_LINKS.map((link) => (
          <NavLink
            key={link.path}
            to={link.path}
            className={({ isActive }) =>
              cn(
                "text-[10px] md:text-xs tracking-wider transition-colors shrink-0",
                isActive 
                  ? "text-[#F5F0E8] font-medium" 
                  : "text-[#C8C2B8] hover:text-[#F5F0E8]"
              )
            }
          >
            {link.name}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
