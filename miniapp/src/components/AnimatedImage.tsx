import React, { useState, useEffect, useMemo, useRef } from 'react';
import Tilt from 'react-parallax-tilt';

interface OrientationData {
  alpha: number;
  beta: number;
  gamma: number;
  isStarted: boolean;
}

interface TiltValues {
  x: number;
  y: number;
}

interface AnimatedImageProps {
  imageUrl: string;
  alt: string;
  rarity: string;
  orientation: OrientationData;
  effectsEnabled: boolean;
  tiltKey: number;
  triggerBurn?: boolean;
  onBurnComplete?: () => void;
}

// Performance constants
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
const toDegrees = (value: number) => (value * 180) / Math.PI;
const createZeroTilt = (): TiltValues => ({ x: 0, y: 0 });
const TILT_LIMIT_DEGREES = 15;
const TILT_SENSITIVITY = 0.3;
const SMOOTHING_THRESHOLD = 0.005;

// Performance detection
const detectDevicePerformance = (): 'high' | 'medium' | 'low' => {
  const hardwareConcurrency = navigator.hardwareConcurrency || 2;
  const memory = (navigator as any).deviceMemory || 4; // eslint-disable-line @typescript-eslint/no-explicit-any
  const userAgent = navigator.userAgent.toLowerCase();
  
  // Check for high-end devices
  if (hardwareConcurrency >= 8 && memory >= 8) return 'high';
  
  // Check for low-end devices
  if (hardwareConcurrency <= 2 || memory <= 2 || 
      userAgent.includes('android 4') || userAgent.includes('android 5')) {
    return 'low';
  }
  
  return 'medium';
};

const DEVICE_PERFORMANCE = detectDevicePerformance();
const ANIMATION_FPS = DEVICE_PERFORMANCE === 'high' ? 60 : DEVICE_PERFORMANCE === 'medium' ? 30 : 15;
const FRAME_INTERVAL = 1000 / ANIMATION_FPS;

const wrapAngleDelta = (angle: number) => {
  if (!Number.isFinite(angle)) {
    return 0;
  }

  const TWO_PI = Math.PI * 2;
  const wrapped = ((angle + Math.PI) % TWO_PI + TWO_PI) % TWO_PI - Math.PI;
  return Number.isFinite(wrapped) ? wrapped : 0;
};

const normalizeAngleDelta = (current: number, reference: number) => {
  if (!Number.isFinite(current) || !Number.isFinite(reference)) {
    return 0;
  }

  return wrapAngleDelta(current - reference);
};

const AnimatedImage: React.FC<AnimatedImageProps> = ({ imageUrl, alt, rarity, orientation, effectsEnabled, tiltKey, triggerBurn = false, onBurnComplete }) => {
  const [referenceOrientation, setReferenceOrientation] = useState<OrientationData | null>(null);
  const [animationState, setAnimationState] = useState({ tick: 0, smoothedTilt: createZeroTilt() });
  const [burnProgress, setBurnProgress] = useState<number>(0);
  const [isBurning, setIsBurning] = useState(false);

  const tiltTargetRef = useRef<TiltValues>(createZeroTilt());
  const smoothingFactorRef = useRef(DEVICE_PERFORMANCE === 'high' ? 0.18 : 0.12);
  const lastFrameTimeRef = useRef<number>(0);
  const animationFrameRef = useRef<number | undefined>(undefined);
  const burnStartTimeRef = useRef<number | null>(null);
  const BURN_DURATION = 5000; // 5 seconds

  // Reset reference when tiltKey changes (new card)
  useEffect(() => {
    setReferenceOrientation(null);
    const resetTilt = createZeroTilt();
    tiltTargetRef.current = resetTilt;
    setAnimationState(prev => ({ ...prev, smoothedTilt: resetTilt }));
  }, [tiltKey]);

  // Set reference on first non-zero orientation reading
  useEffect(() => {
    if (!referenceOrientation && orientation.isStarted &&
        (orientation.alpha !== 0 || orientation.beta !== 0 || orientation.gamma !== 0)) {
      setReferenceOrientation(orientation);
    }
  }, [orientation, referenceOrientation]);

  useEffect(() => {
    const performanceFactor = DEVICE_PERFORMANCE === 'high' ? 0.18 : DEVICE_PERFORMANCE === 'medium' ? 0.15 : 0.12;
    smoothingFactorRef.current = effectsEnabled ? performanceFactor : 0.1;
    if (!effectsEnabled) {
      tiltTargetRef.current = createZeroTilt();
    }
  }, [effectsEnabled]);

  // Burn animation trigger
  useEffect(() => {
    if (triggerBurn && !isBurning) {
      setIsBurning(true);
      burnStartTimeRef.current = null; // Will be set on first frame
      setBurnProgress(0);
      // Reset tilt to center the card
      tiltTargetRef.current = createZeroTilt();
      setAnimationState(prev => ({ ...prev, smoothedTilt: createZeroTilt() }));
    }
  }, [triggerBurn, isBurning]);

  // Consolidated animation loop (includes burn animation)
  useEffect(() => {
    const animate = (currentTime: number) => {
      // Throttle animation based on device performance
      if (currentTime - lastFrameTimeRef.current < FRAME_INTERVAL) {
        animationFrameRef.current = requestAnimationFrame(animate);
        return;
      }
      
      lastFrameTimeRef.current = currentTime;

      // Update burn animation
      if (isBurning) {
        if (burnStartTimeRef.current === null) {
          burnStartTimeRef.current = currentTime;
        }
        
        const elapsed = currentTime - burnStartTimeRef.current;
        const progress = Math.min(elapsed / BURN_DURATION, 1);
        
        setBurnProgress(progress);
        
        if (progress >= 1) {
          // Animation complete - reset
          setIsBurning(false);
          setBurnProgress(0);
          burnStartTimeRef.current = null;
          if (onBurnComplete) {
            onBurnComplete();
          }
        }
      }

      setAnimationState(prevState => {
        const target = tiltTargetRef.current;
        const factor = smoothingFactorRef.current;
        const prevTilt = prevState.smoothedTilt;

        const nextX = prevTilt.x + (target.x - prevTilt.x) * factor;
        const nextY = prevTilt.y + (target.y - prevTilt.y) * factor;

        // Early return if no significant change
        if (Math.abs(nextX - prevTilt.x) < SMOOTHING_THRESHOLD && Math.abs(nextY - prevTilt.y) < SMOOTHING_THRESHOLD) {
          if (Math.abs(target.x) < SMOOTHING_THRESHOLD && Math.abs(target.y) < SMOOTHING_THRESHOLD) {
            return prevState.smoothedTilt.x === 0 && prevState.smoothedTilt.y === 0 
              ? prevState 
              : { ...prevState, smoothedTilt: createZeroTilt() };
          }
          return prevState;
        }

        return {
          tick: prevState.tick + 1,
          smoothedTilt: {
            x: Math.abs(nextX) < SMOOTHING_THRESHOLD ? 0 : nextX,
            y: Math.abs(nextY) < SMOOTHING_THRESHOLD ? 0 : nextY
          }
        };
      });

      animationFrameRef.current = requestAnimationFrame(animate);
    };

    animationFrameRef.current = requestAnimationFrame(animate);
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [isBurning, onBurnComplete]);

  const orientationDelta = useMemo(() => {
    if (!referenceOrientation || !orientation.isStarted) {
      return null;
    }

    return {
      beta: normalizeAngleDelta(orientation.beta, referenceOrientation.beta),
      gamma: normalizeAngleDelta(orientation.gamma, referenceOrientation.gamma)
    };
  }, [orientation, referenceOrientation]);

  const targetTiltAngles = useMemo(() => {
    if (!orientationDelta) {
      return null;
    }

    const tiltX = clamp(toDegrees(orientationDelta.beta) * TILT_SENSITIVITY, -TILT_LIMIT_DEGREES, TILT_LIMIT_DEGREES);
    const tiltY = clamp(toDegrees(orientationDelta.gamma) * TILT_SENSITIVITY, -TILT_LIMIT_DEGREES, TILT_LIMIT_DEGREES);

    return {
      x: tiltX,
      y: tiltY
    };
  }, [orientationDelta]);

  useEffect(() => {
    if (!effectsEnabled) {
      return;
    }

    tiltTargetRef.current = targetTiltAngles ?? createZeroTilt();
  }, [effectsEnabled, targetTiltAngles]);

  const hasLiveTilt = effectsEnabled && !!targetTiltAngles;
  const tiltForEffects = hasLiveTilt ? animationState.smoothedTilt : null;

  const manualTiltAngles = useMemo(() => {
    if (!tiltForEffects) {
      return null;
    }

    return {
      x: -tiltForEffects.x,
      y: tiltForEffects.y
    };
  }, [tiltForEffects]);

  const shadowMetrics = useMemo(() => {
    const baseBlur = 18;
    const baseSpread = 0;
    const baseAlpha = effectsEnabled ? 0.52 : 0.45;

    if (!effectsEnabled) {
      return {
        offsetX: 0,
        offsetY: 14,
        blur: baseBlur,
        spread: baseSpread,
        alpha: baseAlpha
      };
    }

    if (!tiltForEffects) {
      const time = animationState.tick * 0.01;
      return {
        offsetX: Math.sin(time) * 6,
        offsetY: 17 + Math.cos(time * 1.4) * 3,
        blur: baseBlur + 3,
        spread: baseSpread,
        alpha: clamp(baseAlpha + Math.sin(time * 0.9) * 0.04, 0.36, 0.72)
      };
    }

    const offsetX = clamp(-tiltForEffects.y * 1.15, -18, 18);
    const offsetY = clamp(17 + tiltForEffects.x * -1.05, 6, 24);
    const blur = clamp(
      baseBlur + Math.abs(tiltForEffects.x) * 0.75 + Math.abs(tiltForEffects.y) * 0.55,
      12,
      28
    );
    const spread = clamp(
      baseSpread + Math.abs(tiltForEffects.y) * 0.1 + Math.abs(tiltForEffects.x) * 0.05,
      0,
      1
    );
    const magnitudeBoost = (Math.abs(tiltForEffects.x) + Math.abs(tiltForEffects.y)) * 0.018;
    const directionalBoost = clamp((-offsetX / 18) * 0.16, -0.16, 0.16);
    const alpha = clamp(baseAlpha + magnitudeBoost + directionalBoost, 0.4, 0.85);

    return { offsetX, offsetY, blur, spread, alpha };
  }, [animationState.tick, effectsEnabled, tiltForEffects]);

  const tiltContainerStyle = useMemo<React.CSSProperties>(() => ({
    transformStyle: 'preserve-3d'
  }), []);

  const shadowStyle = useMemo<React.CSSProperties>(() => ({
    boxShadow: isBurning ? 'none' : `${shadowMetrics.offsetX}px ${shadowMetrics.offsetY}px ${shadowMetrics.blur}px ${shadowMetrics.spread}px rgba(0, 0, 0, ${shadowMetrics.alpha})`
  }), [shadowMetrics, isBurning]);

  // Memoized shine calculations for better performance
  const shineMetrics = useMemo(() => {
    if (!effectsEnabled) {
      return { x: 50, y: 50, intensity: 0 };
    }
    
    // Get shine intensity based on rarity
    const getShineIntensity = (rarity: string) => {
      const rarityLower = rarity.toLowerCase();
      const baseIntensity = DEVICE_PERFORMANCE === 'high' ? 1.0 : DEVICE_PERFORMANCE === 'medium' ? 0.8 : 0.6;
      switch (rarityLower) {
        case 'common': return 0.33 * baseIntensity;
        case 'rare': return 0.60 * baseIntensity;
        case 'epic': return 0.85 * baseIntensity;
        case 'legendary': return 1.25 * baseIntensity;
        default: return 0.33 * baseIntensity;
      }
    };
    
    if (!tiltForEffects) {
      // Simplified animation for devices without tilt
      const time = animationState.tick * 0.015;
      const motionFactor = DEVICE_PERFORMANCE === 'low' ? 0.5 : 1.0;
      return {
        x: 80 + Math.sin(time) * 3 * motionFactor,
        y: 20 + Math.cos(time * 1.2) * 2 * motionFactor,
        intensity: getShineIntensity(rarity)
      };
    }
    
    const normalizedX = clamp(tiltForEffects.y / TILT_LIMIT_DEGREES, -1, 1);
    const normalizedY = clamp(tiltForEffects.x / TILT_LIMIT_DEGREES, -1, 1);

    return {
      x: clamp(50 + normalizedX * 25, 0, 100),
      y: clamp(50 + normalizedY * 25, 0, 100),
      intensity: getShineIntensity(rarity)
    };
  }, [effectsEnabled, tiltForEffects, animationState.tick, rarity]);

  return (
    <Tilt
      className="card-image-container"
      tiltEnable={effectsEnabled && !isBurning}
      tiltAngleXManual={isBurning ? 0 : (manualTiltAngles ? manualTiltAngles.x : null)}
      tiltAngleYManual={isBurning ? 0 : (manualTiltAngles ? manualTiltAngles.y : null)}
      tiltMaxAngleX={15}
      tiltMaxAngleY={15}
      perspective={1000}
      transitionSpeed={100}
      transitionEasing="ease-out"
      gyroscope={false}
      glareEnable={false}
      style={tiltContainerStyle}
    >
      <div
        className="card-shadow"
        style={shadowStyle}
      />
      <div 
        className={`card-image-content ${isBurning ? 'burning' : ''}`}
        style={isBurning ? { background: 'transparent' } : undefined}
      >
        <img 
          src={imageUrl} 
          alt={alt}
          style={isBurning ? {
            clipPath: `polygon(
              0% ${Math.max(0, 100 - burnProgress * 100 + 2 + Math.sin(burnProgress * 10) * 1.5)}%,
              10% ${Math.max(0, 100 - burnProgress * 100 + 2 + Math.sin(burnProgress * 10 + 0.5) * 2)}%,
              20% ${Math.max(0, 100 - burnProgress * 100 + 2 + Math.sin(burnProgress * 10 + 1) * 1.8)}%,
              30% ${Math.max(0, 100 - burnProgress * 100 + 2 + Math.sin(burnProgress * 10 + 1.5) * 2.2)}%,
              40% ${Math.max(0, 100 - burnProgress * 100 + 2 + Math.sin(burnProgress * 10 + 2) * 1.6)}%,
              50% ${Math.max(0, 100 - burnProgress * 100 + 2 + Math.sin(burnProgress * 10 + 2.5) * 2.1)}%,
              60% ${Math.max(0, 100 - burnProgress * 100 + 2 + Math.sin(burnProgress * 10 + 3) * 1.9)}%,
              70% ${Math.max(0, 100 - burnProgress * 100 + 2 + Math.sin(burnProgress * 10 + 3.5) * 2.3)}%,
              80% ${Math.max(0, 100 - burnProgress * 100 + 2 + Math.sin(burnProgress * 10 + 4) * 1.7)}%,
              90% ${Math.max(0, 100 - burnProgress * 100 + 2 + Math.sin(burnProgress * 10 + 4.5) * 2)}%,
              100% ${Math.max(0, 100 - burnProgress * 100 + 2 + Math.sin(burnProgress * 10 + 5) * 1.8)}%,
              100% 0,
              0 0
            )`,
            background: 'transparent',
            transform: 'scale(1.01)',
            imageRendering: 'crisp-edges',
            WebkitBackfaceVisibility: 'hidden',
            backfaceVisibility: 'hidden'
          } : undefined}
        />
        <div 
          className="card-shine"
          style={{
            opacity: isBurning ? 0 : 1,
            background: DEVICE_PERFORMANCE === 'low' 
              ? `linear-gradient(${75 + (shineMetrics.x - 50) * 0.1}deg,
                  transparent 0%,
                  rgba(255, 255, 255, ${shineMetrics.intensity * 0.15}) ${shineMetrics.x}%,
                  transparent 100%
                )`
              : `linear-gradient(${75 + (shineMetrics.x - 50) * 0.2}deg,
                  transparent 0%,
                  transparent ${Math.max(5, shineMetrics.x - 25)}%,
                  rgba(255, 100, 255, ${shineMetrics.intensity * 0.14}) ${Math.max(10, shineMetrics.x - 20)}%,
                  rgba(100, 200, 255, ${shineMetrics.intensity * 0.18}) ${Math.max(15, shineMetrics.x - 15)}%,
                  rgba(100, 255, 100, ${shineMetrics.intensity * 0.22}) ${Math.max(20, shineMetrics.x - 10)}%,
                  rgba(255, 255, 100, ${shineMetrics.intensity * 0.26}) ${shineMetrics.x}%,
                  rgba(255, 150, 100, ${shineMetrics.intensity * 0.22}) ${Math.min(80, shineMetrics.x + 10)}%,
                  rgba(255, 100, 150, ${shineMetrics.intensity * 0.18}) ${Math.min(85, shineMetrics.x + 15)}%,
                  rgba(200, 100, 255, ${shineMetrics.intensity * 0.14}) ${Math.min(90, shineMetrics.x + 20)}%,
                  transparent ${Math.min(95, shineMetrics.x + 25)}%,
                  transparent 100%
                )`,
            transition: DEVICE_PERFORMANCE === 'high' ? 'background 0.15s ease-out' : 'none'
          }}
        />
        {isBurning && (
          <>
            {/* SVG-based continuous wave with layered strokes for fire effect */}
            <svg
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                width: '100%',
                height: '100%',
                pointerEvents: 'none',
                zIndex: 11,
                mixBlendMode: 'screen'
              }}
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
            >
              {/* Draw multiple paths with different colors and thicknesses for fire effect */}
              {[
                // Bottom: dark base
                { thickness: 2, color: 'rgba(0, 0, 0, 0.6)', blur: 1.5, opacity: 0.4, offset: 2 },
                // Core: bright red/orange
                { thickness: 3, color: 'rgba(200, 20, 0, 1)', blur: 1.5, opacity: 0.95, offset: 0 },
                { thickness: 2.5, color: 'rgba(255, 50, 0, 1)', blur: 1, opacity: 1, offset: 0 },
                // Upper flames: yellow/orange dispersing upward
                { thickness: 4.5, color: 'rgba(255, 150, 30, 0.7)', blur: 2.5, opacity: 0.8, offset: -1.5 },
                { thickness: 6, color: 'rgba(255, 200, 80, 0.4)', blur: 4.5, opacity: 0.65, offset: -3 },
                { thickness: 8, color: 'rgba(255, 240, 150, 0.15)', blur: 6.5, opacity: 0.4, offset: -5.5 },
              ].map((layer, idx) => {
                const pathData = (() => {
                  const points = [];
                  for (let i = 0; i <= 100; i++) {
                    const x = i;
                    const phaseOffset = (i / 100) * 5;
                    const waveAmplitude = 1.5 + 0.5 * Math.sin((i / 100) * Math.PI * 2);
                    const y = Math.max(0, 100 - burnProgress * 100 + 2 + Math.sin(burnProgress * 10 + phaseOffset) * waveAmplitude + layer.offset);
                    points.push(`${i === 0 ? 'M' : 'L'} ${x} ${y}`);
                  }
                  return points.join(' ');
                })();
                
                return (
                  <path
                    key={idx}
                    d={pathData}
                    stroke={layer.color}
                    strokeWidth={layer.thickness}
                    fill="none"
                    opacity={layer.opacity}
                    filter={`blur(${layer.blur}px)`}
                  />
                );
              })}
            </svg>
          </>
        )}
      </div>
    </Tilt>
  );
};

export default AnimatedImage;
