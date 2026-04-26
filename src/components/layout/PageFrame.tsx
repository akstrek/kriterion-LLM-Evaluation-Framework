import { useLocation } from "react-router-dom";
import { Navbar } from "./Navbar";
import { ReactNode } from "react";

interface PageFrameProps {
  children: ReactNode;
}

export function PageFrame({ children }: PageFrameProps) {
  const location = useLocation();
  const isOverview = location.pathname === "/";

  return (
    <div className="w-full h-full relative text-[#F5F0E8] overflow-hidden select-none font-sans bg-[#0A0806]">
      {/* Background Image is set globally or here */}
      <div 
        className="fixed inset-0 w-full h-full z-0 bg-cover bg-center bg-no-repeat"
        style={{ 
          backgroundImage: 'url("/background.webp"), radial-gradient(circle at 70% 30%, #C8873A 0%, rgba(200, 135, 58, 0.4) 30%, rgba(10, 8, 6, 1) 80%), linear-gradient(180deg, #1A120B 0%, #0A0806 100%)' 
        }}
      >
        <div className="absolute bottom-0 left-0 w-[60%] h-[40%]" style={{ clipPath: "polygon(0 100%, 15% 45%, 35% 65%, 55% 20%, 80% 60%, 100% 100%)", background: "linear-gradient(180deg, rgba(15, 13, 11, 0.8) 0%, #0A0806 100%)", filter: "blur(2px)" }}></div>
        <div className="absolute bottom-[28%] left-[45%] w-8 h-16 bg-[#0F0D0B] opacity-90 rounded-t-full" style={{ filter: "drop-shadow(0 0 20px #C8873A)" }}></div>
        <div className="absolute inset-0 bg-white/[0.03] pointer-events-none" style={{ maskImage: "radial-gradient(circle, black, transparent)", WebkitMaskImage: "radial-gradient(circle, black, transparent)" }}></div>
      </div>
      
      {/* Dimming overlay so elements are visible */}
      <div className="fixed inset-0 z-0 bg-black/20 pointer-events-none"></div>

      {/* Global Navigation */}
      <Navbar />

      {/* Product Name Top Left (Hidden on Overview) */}
      {!isOverview && (
        <div className="fixed top-0 left-6 z-50 flex items-center h-[52px] pointer-events-none">
          <span className="font-display font-black text-[20px] text-[#F5F0E8] tracking-[-0.04em]">
            Kriterion
          </span>
        </div>
      )}

      {/* Render children (Animated routes) */}
      {children}
    </div>
  );
}
