export function GrainOverlay() {
  return (
    <div className="fixed inset-0 z-[1] pointer-events-none opacity-[0.35]">
      <svg className="absolute w-full h-full">
        <filter id="noiseFilter">
          <feTurbulence 
            type="fractalNoise" 
            baseFrequency="0.8" 
            numOctaves="3" 
            stitchTiles="stitch"
          />
        </filter>
        <rect width="100%" height="100%" filter="url(#noiseFilter)" />
      </svg>
    </div>
  );
}
