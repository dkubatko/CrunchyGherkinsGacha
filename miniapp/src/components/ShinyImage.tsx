import React, { useState, useEffect } from 'react';

interface OrientationData {
  alpha: number;
  beta: number;
  gamma: number;
  isStarted: boolean;
}

interface ShinyImageProps {
  imageUrl: string;
  alt: string;
  rarity: string;
  orientation: OrientationData;
  effectsEnabled: boolean;
  tiltKey: number;
}

const ShinyImage: React.FC<ShinyImageProps> = ({ imageUrl, alt, rarity, orientation, effectsEnabled, tiltKey }) => {
  const [referenceOrientation, setReferenceOrientation] = useState<OrientationData | null>(null);
  const [animationTick, setAnimationTick] = useState(0);

  // Reset reference when tiltKey changes (new card)
  useEffect(() => {
    setReferenceOrientation(null);
  }, [tiltKey]);

  // Set reference on first non-zero orientation reading
  useEffect(() => {
    if (!referenceOrientation && orientation.isStarted && 
        (orientation.alpha !== 0 || orientation.beta !== 0 || orientation.gamma !== 0)) {
      setReferenceOrientation(orientation);
    }
  }, [orientation, referenceOrientation]);

  // Animation loop for subtle shine effect on PC
  useEffect(() => {
    if (!orientation.isStarted || !referenceOrientation) {
      const interval = setInterval(() => {
        setAnimationTick(tick => tick + 1);
      }, 16); // 60 FPS for smooth animation
      
      return () => clearInterval(interval);
    }
  }, [orientation.isStarted, referenceOrientation]);

  // Calculate tilt transform based on device orientation relative to reference
  const getTiltTransform = () => {
    if (!effectsEnabled || !orientation.isStarted || !referenceOrientation) return '';
    
    const relativeBeta = orientation.beta - referenceOrientation.beta;
    const relativeGamma = orientation.gamma - referenceOrientation.gamma;
    
    const tiltX = (relativeBeta * 180 / Math.PI) * 0.3;
    const tiltY = (relativeGamma * 180 / Math.PI) * 0.3;
    
    const clampedTiltX = Math.max(-15, Math.min(15, tiltX));
    const clampedTiltY = Math.max(-15, Math.min(15, tiltY));
    
    return `perspective(1000px) rotateX(${-clampedTiltX}deg) rotateY(${clampedTiltY}deg)`;
  };

  // Calculate shine position based on device tilt
  const getShinePosition = () => {
    if (!effectsEnabled) {
      return { x: 50, y: 50 };
    }
    
    if (!orientation.isStarted || !referenceOrientation) {
      const time = animationTick * 0.012;
      return { 
        x: 80 + Math.sin(time) * 3,
        y: 20 + Math.cos(time * 1.2) * 2
      };
    }
    
    const relativeBeta = orientation.beta - referenceOrientation.beta;
    const relativeGamma = orientation.gamma - referenceOrientation.gamma;
    
    const x = 50 + (relativeGamma * 25);
    const y = 50 + (relativeBeta * 25);
    
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
    <div 
      className="card-image-container"
      style={{
        transform: getTiltTransform(),
        transition: 'transform 0.1s ease-out',
        transformStyle: 'preserve-3d'
      }}
    >
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
  );
};

export default ShinyImage;
