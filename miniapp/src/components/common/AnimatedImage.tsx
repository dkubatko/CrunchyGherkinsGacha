import React, { useEffect, useRef, useState, useCallback } from 'react';
import type { OrientationData } from '@/types';

// --- Constants ---
const TILT_LIMIT = 15;
const RAD_TO_DEG = 180 / Math.PI;
const TILT_SENSITIVITY = 0.75;
const SMOOTHING = 0.15;
const SMOOTHING_DESKTOP = 1;
const IDLE_THRESHOLD = 0.05;
const BURN_DURATION = 5000;

const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));

const normalizeAngle = (deg: number): number => {
  while (deg > 180) deg -= 360;
  while (deg < -180) deg += 360;
  return deg;
};

const SHINE_INTENSITY: Record<string, number> = {
  common: 0.33, rare: 0.60, epic: 0.85, legendary: 1.25, unique: 1.60,
};

const BURN_LAYERS = [
  { thickness: 2, color: 'rgba(0, 0, 0, 0.6)', blur: 1.5, opacity: 0.4, offset: 2 },
  { thickness: 3, color: 'rgba(200, 20, 0, 1)', blur: 1.5, opacity: 0.95, offset: 0 },
  { thickness: 2.5, color: 'rgba(255, 50, 0, 1)', blur: 1, opacity: 1, offset: 0 },
  { thickness: 4.5, color: 'rgba(255, 150, 30, 0.7)', blur: 2.5, opacity: 0.8, offset: -1.5 },
  { thickness: 6, color: 'rgba(255, 200, 80, 0.4)', blur: 4.5, opacity: 0.65, offset: -3 },
  { thickness: 8, color: 'rgba(255, 240, 150, 0.15)', blur: 6.5, opacity: 0.4, offset: -5.5 },
];

// --- Helpers ---
function buildBurnClipPath(progress: number): string {
  const points: string[] = [];
  for (let i = 0; i <= 10; i++) {
    const wave = Math.sin(progress * 10 + i * 0.5) * (1.5 + 0.5 * Math.sin(i * 0.628));
    points.push(`${i * 10}% ${Math.max(0, 100 - progress * 100 + 2 + wave)}%`);
  }
  return `polygon(${points.join(', ')}, 100% 0%, 0% 0%)`;
}

function buildBurnSvgPath(progress: number, offset: number): string {
  const parts: string[] = [];
  for (let i = 0; i <= 100; i++) {
    const phase = (i / 100) * 5;
    const amp = 1.5 + 0.5 * Math.sin((i / 100) * Math.PI * 2);
    const y = Math.max(0, 100 - progress * 100 + 2 + Math.sin(progress * 10 + phase) * amp + offset);
    parts.push(`${i === 0 ? 'M' : 'L'} ${i} ${y}`);
  }
  return parts.join(' ');
}

function buildShineGradient(isUnique: boolean, angle: number, pos: number, width: number, intensity: number): string {
  const lo = Math.max(0, pos - width);
  const hi = Math.min(100, pos + width);
  if (isUnique) {
    return `linear-gradient(${angle}deg,
      transparent ${lo}%,
      rgba(255, 0, 0, ${intensity * 0.12}) ${pos - width * 0.6}%,
      rgba(255, 255, 0, ${intensity * 0.12}) ${pos - width * 0.4}%,
      rgba(0, 255, 0, ${intensity * 0.12}) ${pos - width * 0.2}%,
      rgba(0, 255, 255, ${intensity * 0.25}) ${pos}%,
      rgba(0, 0, 255, ${intensity * 0.12}) ${pos + width * 0.2}%,
      rgba(255, 0, 255, ${intensity * 0.12}) ${pos + width * 0.4}%,
      transparent ${hi}%)`;
  }
  return `linear-gradient(${angle}deg,
    transparent ${lo}%,
    rgba(255, 180, 180, ${intensity * 0.15}) ${pos - width * 0.65}%,
    rgba(180, 255, 180, ${intensity * 0.15}) ${pos - width * 0.35}%,
    rgba(255, 255, 255, ${intensity * 0.5}) ${pos}%,
    rgba(180, 180, 255, ${intensity * 0.15}) ${pos + width * 0.35}%,
    rgba(255, 180, 255, ${intensity * 0.15}) ${pos + width * 0.65}%,
    transparent ${hi}%)`;
}

// --- Component ---
interface AnimatedImageProps {
  imageUrl: string;
  alt: string;
  rarity: string;
  orientation: OrientationData;
  effectsEnabled: boolean;
  tiltKey: number;
  triggerBurn?: boolean;
  onBurnComplete?: () => void;
  borderRadius?: string;
  square?: boolean;
}

const AnimatedImage: React.FC<AnimatedImageProps> = ({
  imageUrl, alt, rarity, orientation, effectsEnabled, tiltKey,
  triggerBurn = false, onBurnComplete, borderRadius, square,
}) => {
  // DOM refs — written to directly in rAF, bypassing React renders
  const containerRef = useRef<HTMLDivElement>(null);
  const shadowRef = useRef<HTMLDivElement>(null);
  const shineRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const burnSvgRef = useRef<SVGSVGElement>(null);
  const burnPathsRef = useRef<SVGPathElement[]>([]);

  // Animation state — all refs, zero React overhead per frame
  const tiltCurrent = useRef({ x: 0, y: 0 });
  const tiltTarget = useRef({ x: 0, y: 0 });
  const reference = useRef<{ beta: number; gamma: number } | null>(null);
  const tick = useRef(0);
  const frameId = useRef<number>(0);
  const shineOff = useRef(false);
  const restingRef = useRef(false);

  // Props synced to refs for rAF access without recreating the loop
  const effectsRef = useRef(effectsEnabled);
  const orientationRef = useRef(orientation);
  const onBurnCompleteRef = useRef(onBurnComplete);

  // Burn — only React state needed (controls conditional SVG rendering)
  const [isBurning, setIsBurning] = useState(false);
  const burningRef = useRef(false);
  const burnStartRef = useRef<number | null>(null);

  const isUnique = rarity.toLowerCase() === 'unique';
  const intensity = SHINE_INTENSITY[rarity.toLowerCase()] ?? 0.33;

  // Sync props → refs
  useEffect(() => { effectsRef.current = effectsEnabled; }, [effectsEnabled]);
  useEffect(() => { orientationRef.current = orientation; }, [orientation]);
  useEffect(() => { onBurnCompleteRef.current = onBurnComplete; }, [onBurnComplete]);

  // ==========================================================================
  // Animation loop — runs on mount, writes directly to DOM via refs.
  // Never calls setState during animation (except once on burn completion).
  // ==========================================================================
  useEffect(() => {
    const render = () => {
      const el = containerRef.current;
      if (!el) { frameId.current = requestAnimationFrame(render); return; }

      const cur = tiltCurrent.current;
      const tgt = tiltTarget.current;
      const effects = effectsRef.current;
      const isDesktop = !orientationRef.current.isStarted;

      // Exponential smoothing toward target (faster on desktop for snappier mouse response)
      const smoothing = isDesktop ? SMOOTHING_DESKTOP : SMOOTHING;
      cur.x += (tgt.x - cur.x) * smoothing;
      cur.y += (tgt.y - cur.y) * smoothing;
      if (Math.abs(cur.x) < IDLE_THRESHOLD && Math.abs(tgt.x) < IDLE_THRESHOLD) cur.x = 0;
      if (Math.abs(cur.y) < IDLE_THRESHOLD && Math.abs(tgt.y) < IDLE_THRESHOLD) cur.y = 0;

      const hasTilt = Math.abs(cur.x) > 0.1 || Math.abs(cur.y) > 0.1;
      const isIdle = !hasTilt && Math.abs(tgt.x) < IDLE_THRESHOLD && Math.abs(tgt.y) < IDLE_THRESHOLD;

      // Desktop optimization: write resting state once, then skip frames
      if (isDesktop && isIdle && !burningRef.current && effects) {
        if (restingRef.current) {
          frameId.current = requestAnimationFrame(render);
          return;
        }
        el.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg)';
        if (shadowRef.current) shadowRef.current.style.boxShadow = '0px 14px 18px 0px rgba(0, 0, 0, 0.45)';
        if (shineRef.current) {
          shineRef.current.style.opacity = '1';
          shineRef.current.style.background = buildShineGradient(isUnique, 120, 54, 45, intensity);
        }
        restingRef.current = true;
        frameId.current = requestAnimationFrame(render);
        return;
      }
      restingRef.current = false;

      tick.current++;

      // --- Tilt transform ---
      el.style.transform = `perspective(1000px) rotateX(${cur.x}deg) rotateY(${-cur.y}deg)`;

      // --- Shadow ---
      const sh = shadowRef.current;
      if (sh) {
        if (burningRef.current) {
          sh.style.boxShadow = 'none';
        } else if (!effects) {
          sh.style.boxShadow = '0px 14px 18px 0px rgba(0, 0, 0, 0.45)';
        } else if (hasTilt) {
          const ox = clamp(cur.y * 1.2, -20, 20);
          const oy = clamp(14 - cur.x * 0.8, 4, 24);
          const mag = Math.sqrt(cur.x ** 2 + cur.y ** 2);
          const blur = clamp(18 + mag * 0.5, 14, 26);
          const alpha = clamp(0.52 + mag * 0.015, 0.4, 0.75);
          sh.style.boxShadow = `${ox}px ${oy}px ${blur}px 0px rgba(0, 0, 0, ${alpha})`;
        } else {
          // Mobile idle: gentle shadow oscillation
          const t = tick.current * 0.01;
          sh.style.boxShadow = `${Math.sin(t) * 6}px ${17 + Math.cos(t * 1.4) * 3}px 21px 0px rgba(0, 0, 0, ${clamp(0.52 + Math.sin(t * 0.9) * 0.04, 0.36, 0.72)})`;
        }
      }

      // --- Shine ---
      const sn = shineRef.current;
      if (sn) {
        if (!effects || burningRef.current || shineOff.current) {
          sn.style.opacity = '0';
        } else if (hasTilt) {
          sn.style.opacity = '1';
          const drive = clamp(cur.x / TILT_LIMIT, -1, 1) + clamp(cur.y / TILT_LIMIT, -1, 1);
          const pos = 54 + drive * 50;
          const angle = 120 + clamp(cur.y / TILT_LIMIT, -1, 1) * 10;
          const width = 55 + Math.abs(drive) * 25;
          sn.style.background = buildShineGradient(isUnique, angle, pos, width, intensity);
        } else {
          // Mobile idle: gentle shine sweep (desktop idle handled by resting path above)
          sn.style.opacity = '1';
          const pos = 54 + Math.sin(tick.current * 0.02) * 30;
          sn.style.background = buildShineGradient(isUnique, 120, pos, 45, intensity);
        }
      }

      // --- Burn ---
      if (burningRef.current) {
        if (burnStartRef.current === null) burnStartRef.current = performance.now();
        const progress = Math.min((performance.now() - burnStartRef.current) / BURN_DURATION, 1);

        const img = imageRef.current;
        if (img) {
          img.style.clipPath = buildBurnClipPath(progress);
          img.style.transform = 'scale(1.01)';
        }

        burnPathsRef.current.forEach((path, i) => {
          if (path && BURN_LAYERS[i]) {
            path.setAttribute('d', buildBurnSvgPath(progress, BURN_LAYERS[i].offset));
          }
        });

        if (progress >= 1) {
          burningRef.current = false;
          burnStartRef.current = null;
          if (img) { img.style.clipPath = ''; img.style.transform = ''; }
          setIsBurning(false);
          onBurnCompleteRef.current?.();
        }
      }

      frameId.current = requestAnimationFrame(render);
    };

    frameId.current = requestAnimationFrame(render);
    return () => { if (frameId.current) cancelAnimationFrame(frameId.current); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Cache burn SVG paths after React renders the SVG
  useEffect(() => {
    if (isBurning && burnSvgRef.current) {
      burnPathsRef.current = Array.from(burnSvgRef.current.querySelectorAll('path'));
    } else {
      burnPathsRef.current = [];
    }
  }, [isBurning]);

  // ==========================================================================
  // Effects — update refs that the animation loop reads
  // ==========================================================================

  // Orientation → tilt target
  useEffect(() => {
    if (!effectsEnabled || !orientation.isStarted || !reference.current || burningRef.current) {
      tiltTarget.current = { x: 0, y: 0 };
      return;
    }
    const db = normalizeAngle((orientation.beta - reference.current.beta) * RAD_TO_DEG);
    const dg = normalizeAngle((orientation.gamma - reference.current.gamma) * RAD_TO_DEG);
    tiltTarget.current = {
      x: clamp(db * TILT_SENSITIVITY, -TILT_LIMIT, TILT_LIMIT),
      y: clamp(dg * TILT_SENSITIVITY, -TILT_LIMIT, TILT_LIMIT),
    };
  }, [orientation, effectsEnabled]);

  // Capture reference on first valid orientation reading
  useEffect(() => {
    if (!reference.current && orientation.isStarted &&
        (orientation.beta !== 0 || orientation.gamma !== 0)) {
      reference.current = { beta: orientation.beta, gamma: orientation.gamma };
    }
  }, [orientation]);

  // Reset on card change
  useEffect(() => {
    reference.current = null;
    tiltTarget.current = { x: 0, y: 0 };
    tiltCurrent.current = { x: 0, y: 0 };
  }, [tiltKey]);

  // Effects disabled → reset tilt and reference
  useEffect(() => {
    if (!effectsEnabled) {
      tiltTarget.current = { x: 0, y: 0 };
      tiltCurrent.current = { x: 0, y: 0 };
      reference.current = null;
    }
  }, [effectsEnabled]);

  // Burn trigger
  useEffect(() => {
    if (triggerBurn && !burningRef.current) {
      burningRef.current = true;
      burnStartRef.current = null;
      tiltTarget.current = { x: 0, y: 0 };
      tiltCurrent.current = { x: 0, y: 0 };
      setIsBurning(true);
    }
  }, [triggerBurn]);

  // ==========================================================================
  // Event handlers
  // ==========================================================================

  // Desktop mouse tilt (skipped when device orientation is active)
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!effectsRef.current || orientationRef.current.isStarted || burningRef.current) return;
    restingRef.current = false;
    const rect = e.currentTarget.getBoundingClientRect();
    const nx = ((e.clientY - rect.top) / rect.height - 0.5) * 2;
    const ny = ((e.clientX - rect.left) / rect.width - 0.5) * 2;
    tiltTarget.current = { x: nx * TILT_LIMIT, y: ny * TILT_LIMIT };
  }, []);

  const handleMouseLeave = useCallback(() => {
    if (!orientationRef.current.isStarted) {
      tiltTarget.current = { x: 0, y: 0 };
    }
  }, []);

  // Tap to recalibrate — makes current device position the new "flat"
  const handleClick = useCallback(() => {
    const ori = orientationRef.current;
    if (!ori.isStarted) return;
    shineOff.current = true;
    setTimeout(() => {
      reference.current = { beta: ori.beta, gamma: ori.gamma };
      tiltTarget.current = { x: 0, y: 0 };
      tiltCurrent.current = { x: 0, y: 0 };
      setTimeout(() => { shineOff.current = false; }, 100);
    }, 100);
  }, []);

  // ==========================================================================
  // Render
  // ==========================================================================
  const contentStyle: React.CSSProperties = {
    ...(borderRadius ? { borderRadius, clipPath: `inset(0 round ${borderRadius})` } : {}),
    ...(square ? { aspectRatio: '1' } : {}),
    ...(isBurning ? { background: 'transparent' } : {}),
  };

  return (
    <div
      ref={containerRef}
      className="card-image-container"
      style={{ transformStyle: 'preserve-3d', willChange: 'transform' }}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      <div
        ref={shadowRef}
        className="card-shadow"
        style={borderRadius ? { borderRadius } : undefined}
      />
      <div
        className={`card-image-content ${isBurning ? 'burning' : ''}`}
        style={contentStyle}
      >
        <img
          ref={imageRef}
          src={imageUrl}
          alt={alt}
          style={isBurning
            ? { background: 'transparent', imageRendering: 'crisp-edges', WebkitBackfaceVisibility: 'hidden', backfaceVisibility: 'hidden', ...(borderRadius ? { borderRadius } : {}) }
            : (borderRadius ? { borderRadius } : undefined)
          }
        />
        <div
          ref={shineRef}
          className="card-shine"
          style={{ mixBlendMode: 'overlay' }}
        />
        {isBurning && (
          <svg
            ref={burnSvgRef}
            style={{ position: 'absolute', left: 0, top: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 11, mixBlendMode: 'screen' }}
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
          >
            {BURN_LAYERS.map((layer, i) => (
              <path
                key={i}
                stroke={layer.color}
                strokeWidth={layer.thickness}
                fill="none"
                opacity={layer.opacity}
                filter={`blur(${layer.blur}px)`}
              />
            ))}
          </svg>
        )}
      </div>
    </div>
  );
};

export default AnimatedImage;
