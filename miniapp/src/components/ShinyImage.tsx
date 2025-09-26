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

interface ShinyImageProps {
  imageUrl: string;
  alt: string;
  rarity: string;
  orientation: OrientationData;
  effectsEnabled: boolean;
  tiltKey: number;
}

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
const toDegrees = (value: number) => (value * 180) / Math.PI;
const createZeroTilt = (): TiltValues => ({ x: 0, y: 0 });
const TILT_LIMIT_DEGREES = 15;
const TILT_SENSITIVITY = 0.3;
const SMOOTHING_THRESHOLD = 0.005;

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

const ShinyImage: React.FC<ShinyImageProps> = ({ imageUrl, alt, rarity, orientation, effectsEnabled, tiltKey }) => {
  const [referenceOrientation, setReferenceOrientation] = useState<OrientationData | null>(null);
  const [animationTick, setAnimationTick] = useState(0);
  const [smoothedTilt, setSmoothedTilt] = useState<TiltValues>(createZeroTilt);

  const tiltTargetRef = useRef<TiltValues>(createZeroTilt());
  const smoothingFactorRef = useRef(0.18);

  // Reset reference when tiltKey changes (new card)
  useEffect(() => {
    setReferenceOrientation(null);
    const resetTilt = createZeroTilt();
    tiltTargetRef.current = resetTilt;
    setSmoothedTilt(resetTilt);
  }, [tiltKey]);

  // Set reference on first non-zero orientation reading
  useEffect(() => {
    if (!referenceOrientation && orientation.isStarted &&
        (orientation.alpha !== 0 || orientation.beta !== 0 || orientation.gamma !== 0)) {
      setReferenceOrientation(orientation);
    }
  }, [orientation, referenceOrientation]);

  useEffect(() => {
    smoothingFactorRef.current = effectsEnabled ? 0.18 : 0.1;
    if (!effectsEnabled) {
      tiltTargetRef.current = createZeroTilt();
    }
  }, [effectsEnabled]);

  // Animation loop for subtle shine effect on PC
  useEffect(() => {
    if (!orientation.isStarted || !referenceOrientation) {
      const interval = setInterval(() => {
        setAnimationTick(tick => tick + 1);
      }, 16); // 60 FPS for smooth animation
      
      return () => clearInterval(interval);
    }
  }, [orientation.isStarted, referenceOrientation]);

  useEffect(() => {
    let animationFrame: number;

    const updateTilt = () => {
      setSmoothedTilt(prev => {
        const target = tiltTargetRef.current;
        const factor = smoothingFactorRef.current;

        const nextX = prev.x + (target.x - prev.x) * factor;
        const nextY = prev.y + (target.y - prev.y) * factor;

        if (Math.abs(nextX - prev.x) < SMOOTHING_THRESHOLD && Math.abs(nextY - prev.y) < SMOOTHING_THRESHOLD) {
          if (Math.abs(target.x) < SMOOTHING_THRESHOLD && Math.abs(target.y) < SMOOTHING_THRESHOLD) {
            if (prev.x === 0 && prev.y === 0) {
              return prev;
            }
            return createZeroTilt();
          }

          return prev;
        }

        return {
          x: Math.abs(nextX) < SMOOTHING_THRESHOLD ? 0 : nextX,
          y: Math.abs(nextY) < SMOOTHING_THRESHOLD ? 0 : nextY
        };
      });

      animationFrame = requestAnimationFrame(updateTilt);
    };

    animationFrame = requestAnimationFrame(updateTilt);
    return () => cancelAnimationFrame(animationFrame);
  }, []);

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
  const tiltForEffects = hasLiveTilt ? smoothedTilt : null;

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
      const time = animationTick * 0.01;
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
  }, [animationTick, effectsEnabled, tiltForEffects]);

  const tiltContainerStyle = useMemo<React.CSSProperties>(() => ({
    transformStyle: 'preserve-3d'
  }), []);

  const shadowStyle = useMemo<React.CSSProperties>(() => ({
    boxShadow: `${shadowMetrics.offsetX}px ${shadowMetrics.offsetY}px ${shadowMetrics.blur}px ${shadowMetrics.spread}px rgba(0, 0, 0, ${shadowMetrics.alpha})`
  }), [shadowMetrics]);

  // Calculate shine position based on device tilt
  const getShinePosition = () => {
    if (!effectsEnabled) {
      return { x: 50, y: 50 };
    }
    
    if (!tiltForEffects) {
      const time = animationTick * 0.012;
      return { 
        x: 80 + Math.sin(time) * 3,
        y: 20 + Math.cos(time * 1.2) * 2
      };
    }
    
    const normalizedX = clamp(tiltForEffects.y / TILT_LIMIT_DEGREES, -1, 1);
    const normalizedY = clamp(tiltForEffects.x / TILT_LIMIT_DEGREES, -1, 1);

    const x = 50 + normalizedX * 25;
    const y = 50 + normalizedY * 25;

    const clampedX = Math.max(0, Math.min(100, x));
    const clampedY = Math.max(0, Math.min(100, y));

    return { x: clampedX, y: clampedY };
  };

  // Get shine intensity based on rarity
  const getShineIntensity = (rarity: string) => {
    const rarityLower = rarity.toLowerCase();
    switch (rarityLower) {
      case 'common': return 0.33;
      case 'rare': return 0.60;
      case 'epic': return 0.85;
      case 'legendary': return 1.25;
      default: return 0.33;
    }
  };

  const shinePosition = getShinePosition();
  const shineIntensity = effectsEnabled ? getShineIntensity(rarity) : 0;

  return (
    <Tilt
      className="card-image-container"
      tiltEnable={effectsEnabled}
      tiltAngleXManual={manualTiltAngles ? manualTiltAngles.x : null}
      tiltAngleYManual={manualTiltAngles ? manualTiltAngles.y : null}
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
      <div className="card-image-content">
        <img 
          src={imageUrl} 
          alt={alt}
        />
        <div 
          className="card-shine"
          style={{
            background: `
              linear-gradient(${75 + (shinePosition.x - 50) * 0.2}deg,
                transparent 0%,
                transparent ${Math.max(5, shinePosition.x - 25)}%,
                rgba(255, 100, 255, ${shineIntensity * 0.14}) ${Math.max(10, shinePosition.x - 20)}%,
                rgba(100, 200, 255, ${shineIntensity * 0.18}) ${Math.max(15, shinePosition.x - 15)}%,
                rgba(100, 255, 100, ${shineIntensity * 0.22}) ${Math.max(20, shinePosition.x - 10)}%,
                rgba(255, 255, 100, ${shineIntensity * 0.26}) ${shinePosition.x}%,
                rgba(255, 150, 100, ${shineIntensity * 0.22}) ${Math.min(80, shinePosition.x + 10)}%,
                rgba(255, 100, 150, ${shineIntensity * 0.18}) ${Math.min(85, shinePosition.x + 15)}%,
                rgba(200, 100, 255, ${shineIntensity * 0.14}) ${Math.min(90, shinePosition.x + 20)}%,
                transparent ${Math.min(95, shinePosition.x + 25)}%,
                transparent 100%
              )
            `,
            transition: 'background 0.15s ease-out'
          }}
        />
      </div>
    </Tilt>
  );
};

export default ShinyImage;
