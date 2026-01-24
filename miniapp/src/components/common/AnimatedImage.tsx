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
const createZeroTilt = (): TiltValues => ({ x: 0, y: 0 });
const TILT_LIMIT_DEGREES = 15;
const RAD_TO_DEG = 180 / Math.PI; // Telegram DeviceOrientation returns radians

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
const ANIMATION_FPS = DEVICE_PERFORMANCE === 'high' ? 60 : DEVICE_PERFORMANCE === 'medium' ? 60 : 30;
const FRAME_INTERVAL = 1000 / ANIMATION_FPS;

// Normalize angle to -180 to 180 range
const normalizeAngle = (angle: number): number => {
  while (angle > 180) angle -= 360;
  while (angle < -180) angle += 360;
  return angle;
};

const AnimatedImage: React.FC<AnimatedImageProps> = ({ imageUrl, alt, rarity, orientation, effectsEnabled, tiltKey, triggerBurn = false, onBurnComplete }) => {
  const [animationState, setAnimationState] = useState({ tick: 0, smoothedTilt: createZeroTilt() });
  const [burnProgress, setBurnProgress] = useState<number>(0);
  const [isBurning, setIsBurning] = useState(false);
  const [referenceOrientation, setReferenceOrientation] = useState<{ beta: number; gamma: number } | null>(null);
  const [isShineDisabledForReset, setIsShineDisabledForReset] = useState(false);

  const tiltTargetRef = useRef<TiltValues>(createZeroTilt());
  const smoothingFactorRef = useRef(DEVICE_PERFORMANCE === 'high' ? 0.15 : 0.12);
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

  // Capture reference orientation on first valid reading
  useEffect(() => {
    if (!referenceOrientation && orientation.isStarted && 
        (orientation.beta !== 0 || orientation.gamma !== 0)) {
      setReferenceOrientation({
        beta: orientation.beta,
        gamma: orientation.gamma
      });
    }
  }, [orientation, referenceOrientation]);

  useEffect(() => {
    const performanceFactor = DEVICE_PERFORMANCE === 'high' ? 0.15 : DEVICE_PERFORMANCE === 'medium' ? 0.12 : 0.1;
    smoothingFactorRef.current = effectsEnabled ? performanceFactor : 0.1;
    if (!effectsEnabled) {
      tiltTargetRef.current = createZeroTilt();
    }
  }, [effectsEnabled]);

  // Burn animation trigger
  useEffect(() => {
    if (triggerBurn && !isBurning) {
      setIsBurning(true);
      burnStartTimeRef.current = null;
      setBurnProgress(0);
      tiltTargetRef.current = createZeroTilt();
      setAnimationState(prev => ({ ...prev, smoothedTilt: createZeroTilt() }));
    }
  }, [triggerBurn, isBurning]);

  // Calculate target tilt from device orientation
  useEffect(() => {
    if (!effectsEnabled || !orientation.isStarted || !referenceOrientation || isBurning) {
      tiltTargetRef.current = createZeroTilt();
      return;
    }

    // Calculate delta from reference position
    // Beta: front-to-back tilt (-180 to 180), positive = device tilted forward
    // Gamma: left-to-right tilt (-90 to 90), positive = device tilted right
    // Telegram returns values in RADIANS, so convert to degrees first
    const deltaBeta = normalizeAngle((orientation.beta - referenceOrientation.beta) * RAD_TO_DEG);
    const deltaGamma = normalizeAngle((orientation.gamma - referenceOrientation.gamma) * RAD_TO_DEG);

    // Map orientation to card tilt:
    // - Tilting device forward/back (beta) -> card tilts on X axis (pitch)
    // - Tilting device left/right (gamma) -> card tilts on Y axis (roll)
    // After converting from radians, values are in actual degrees
    // Slightly dampen for smoother feel (0.75x means 20° device tilt = 15° card tilt)
    const TILT_SENSITIVITY = 0.75;
    const tiltX = clamp(deltaBeta * TILT_SENSITIVITY, -TILT_LIMIT_DEGREES, TILT_LIMIT_DEGREES);
    const tiltY = clamp(deltaGamma * TILT_SENSITIVITY, -TILT_LIMIT_DEGREES, TILT_LIMIT_DEGREES);

    tiltTargetRef.current = { x: tiltX, y: tiltY };
  }, [orientation, referenceOrientation, effectsEnabled, isBurning]);

  // Consolidated animation loop
  useEffect(() => {
    const animate = (currentTime: number) => {
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

        // Skip update if change is negligible
        const threshold = 0.01;
        if (Math.abs(nextX - prevTilt.x) < threshold && Math.abs(nextY - prevTilt.y) < threshold) {
          return prevState;
        }

        return {
          tick: prevState.tick + 1,
          smoothedTilt: { x: nextX, y: nextY }
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

  const hasLiveTilt = effectsEnabled && orientation.isStarted && !!referenceOrientation;
  const tiltForEffects = hasLiveTilt ? animationState.smoothedTilt : null;

  const manualTiltAngles = useMemo(() => {
    if (!tiltForEffects) {
      return null;
    }

    // Map smoothed tilt values to react-parallax-tilt angles
    // X: forward/back device tilt -> card pitch (rotate around horizontal axis)
    // Y: left/right device tilt -> card roll (rotate around vertical axis)
    return {
      x: clamp(tiltForEffects.x, -TILT_LIMIT_DEGREES, TILT_LIMIT_DEGREES),
      y: clamp(-tiltForEffects.y, -TILT_LIMIT_DEGREES, TILT_LIMIT_DEGREES)
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

    // Shadow moves opposite to the tilt direction (light source from above)
    const offsetX = clamp(tiltForEffects.y * 1.2, -20, 20);
    const offsetY = clamp(14 - tiltForEffects.x * 0.8, 4, 24);
    const blur = clamp(
      baseBlur + Math.abs(tiltForEffects.x) * 0.5 + Math.abs(tiltForEffects.y) * 0.5,
      14,
      26
    );
    const spread = clamp(
      baseSpread + (Math.abs(tiltForEffects.y) + Math.abs(tiltForEffects.x)) * 0.03,
      0,
      2
    );
    const tiltMagnitude = Math.sqrt(tiltForEffects.x ** 2 + tiltForEffects.y ** 2);
    const alpha = clamp(baseAlpha + tiltMagnitude * 0.015, 0.4, 0.75);

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
    if (!effectsEnabled || isShineDisabledForReset) {
      return { pos: 50, angle: 115, intensity: 0, width: 0 };
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
        case 'unique': return 1.60 * baseIntensity;
        default: return 0.33 * baseIntensity;
      }
    };
    
    const intensity = getShineIntensity(rarity);

    if (!tiltForEffects) {
      // Simplified animation for devices without tilt
      const time = animationState.tick * 0.02;
      return {
        pos: 54 + Math.sin(time) * 30,
        angle: 120,
        intensity,
        width: 45
      };
    }
    
    // Calculate shine position based on tilt (reflection logic)
    // Tilt Left (y < 0) -> Shine moves Left (pos < 50)
    // Tilt Up (x < 0) -> Shine moves Up (pos < 50)
    const normalizedX = clamp(tiltForEffects.x / TILT_LIMIT_DEGREES, -1, 1); // Pitch
    const normalizedY = clamp(tiltForEffects.y / TILT_LIMIT_DEGREES, -1, 1); // Roll

    // Combine for a diagonal sweep (120 deg is top-left to bottom-right)
    const drive = normalizedX + normalizedY; 
    
    return {
      pos: 54 + drive * 50,
      angle: 120 + (normalizedY * 10),
      intensity,
      width: 55 + Math.abs(drive) * 25
    };
  }, [effectsEnabled, tiltForEffects, animationState.tick, rarity, isShineDisabledForReset]);

  // Reset reference orientation on tap - makes current position the new "flat" view
  // First disables shine, then resets tilt after a brief delay
  const handleTap = () => {
    if (orientation.isStarted) {
      // First disable shine
      setIsShineDisabledForReset(true);
      
      // Wait for shine to visually disappear, then reset tilt
      setTimeout(() => {
        setReferenceOrientation({
          beta: orientation.beta,
          gamma: orientation.gamma
        });
        // Reset smoothed tilt to zero for immediate flat appearance
        tiltTargetRef.current = createZeroTilt();
        setAnimationState(prev => ({ ...prev, smoothedTilt: createZeroTilt() }));
        
        // Re-enable shine after tilt has settled
        setTimeout(() => {
          setIsShineDisabledForReset(false);
        }, 100);
      }, 100);
    }
  };

  return (
    <Tilt
      className="card-image-container"
      tiltEnable={effectsEnabled && !isBurning}
      tiltAngleXManual={isBurning ? 0 : manualTiltAngles?.x}
      tiltAngleYManual={isBurning ? 0 : manualTiltAngles?.y}
      tiltMaxAngleX={15}
      tiltMaxAngleY={15}
      perspective={1000}
      transitionSpeed={100}
      transitionEasing="ease-out"
      gyroscope={false}
      glareEnable={false}
      style={tiltContainerStyle}
      onEnter={handleTap}
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
              ? `linear-gradient(${shineMetrics.angle}deg,
                  transparent ${shineMetrics.pos - shineMetrics.width}%,
                  rgba(255, 255, 255, ${shineMetrics.intensity * 0.3}) ${shineMetrics.pos}%,
                  transparent ${shineMetrics.pos + shineMetrics.width}%
                )`
              : rarity.toLowerCase() === 'unique'
                ? `linear-gradient(${shineMetrics.angle}deg,
                    transparent ${Math.max(0, shineMetrics.pos - shineMetrics.width)}%,
                    rgba(255, 0, 0, ${shineMetrics.intensity * 0.12}) ${shineMetrics.pos - shineMetrics.width * 0.6}%,
                    rgba(255, 255, 0, ${shineMetrics.intensity * 0.12}) ${shineMetrics.pos - shineMetrics.width * 0.4}%,
                    rgba(0, 255, 0, ${shineMetrics.intensity * 0.12}) ${shineMetrics.pos - shineMetrics.width * 0.2}%,
                    rgba(0, 255, 255, ${shineMetrics.intensity * 0.25}) ${shineMetrics.pos}%,
                    rgba(0, 0, 255, ${shineMetrics.intensity * 0.12}) ${shineMetrics.pos + shineMetrics.width * 0.2}%,
                    rgba(255, 0, 255, ${shineMetrics.intensity * 0.12}) ${shineMetrics.pos + shineMetrics.width * 0.4}%,
                    transparent ${Math.min(100, shineMetrics.pos + shineMetrics.width)}%
                  )`
                : `linear-gradient(${shineMetrics.angle}deg,
                    transparent ${Math.max(0, shineMetrics.pos - shineMetrics.width)}%,
                    rgba(255, 180, 180, ${shineMetrics.intensity * 0.15}) ${shineMetrics.pos - shineMetrics.width * 0.65}%,
                    rgba(180, 255, 180, ${shineMetrics.intensity * 0.15}) ${shineMetrics.pos - shineMetrics.width * 0.35}%,
                    rgba(255, 255, 255, ${shineMetrics.intensity * 0.5}) ${shineMetrics.pos}%,
                    rgba(180, 180, 255, ${shineMetrics.intensity * 0.15}) ${shineMetrics.pos + shineMetrics.width * 0.35}%,
                    rgba(255, 180, 255, ${shineMetrics.intensity * 0.15}) ${shineMetrics.pos + shineMetrics.width * 0.65}%,
                    transparent ${Math.min(100, shineMetrics.pos + shineMetrics.width)}%
                  )`,
            transition: DEVICE_PERFORMANCE === 'high' ? 'background 0.1s ease-out' : 'none',
            mixBlendMode: 'overlay'
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
