import React, { useState, useEffect } from 'react';

interface OrientationData {
  alpha: number;
  beta: number;
  gamma: number;
  isStarted: boolean;
}

interface CardProps {
  rarity: string;
  modifier: string;
  base_name: string;
  image_b64: string;
  orientation: OrientationData;
  tiltKey: number;
  id: number;
}

const Card: React.FC<CardProps> = ({ rarity, modifier, base_name, image_b64, orientation, tiltKey, id }) => {
  const [referenceOrientation, setReferenceOrientation] = useState<OrientationData | null>(null);
  const [animationTick, setAnimationTick] = useState(0);
  const [effectsEnabled, setEffectsEnabled] = useState(true);

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
    
    // Calculate relative changes from reference point
    const relativeBeta = orientation.beta - referenceOrientation.beta;
    const relativeGamma = orientation.gamma - referenceOrientation.gamma;
    
    // Convert radians to degrees and apply subtle scaling
    const tiltX = (relativeBeta * 180 / Math.PI) * 0.3; // Scale down for subtlety
    const tiltY = (relativeGamma * 180 / Math.PI) * 0.3;
    
    // Clamp values to prevent extreme tilting
    const clampedTiltX = Math.max(-15, Math.min(15, tiltX));
    const clampedTiltY = Math.max(-15, Math.min(15, tiltY));
    
    return `perspective(1000px) rotateX(${-clampedTiltX}deg) rotateY(${clampedTiltY}deg)`;
  };

  // Calculate shine position based on device tilt
  const getShinePosition = () => {
    if (!effectsEnabled) {
      return { x: 50, y: 50 }; // Return center position when effects are disabled
    }
    
    if (!orientation.isStarted || !referenceOrientation) {
      // Subtle movement on PC - very gentle oscillation around upper right corner
      const time = animationTick * 0.012; // 20% faster (was 0.01, now 0.012)
      return { 
        x: 80 + Math.sin(time) * 3, // Moved further right (was 70, now 80)
        y: 20 + Math.cos(time * 1.2) * 2 // Moved further up (was 30, now 20)
      };
    }
    
    // Calculate relative changes from reference point
    const relativeBeta = orientation.beta - referenceOrientation.beta;
    const relativeGamma = orientation.gamma - referenceOrientation.gamma;
    
    // Convert to percentage position with much higher sensitivity for agile movement
    const x = 50 + (relativeGamma * 25); // Center base position, high sensitivity
    const y = 50 + (relativeBeta * 25); // Center base position, high sensitivity
    
    // Allow movement across entire card face
    const clampedX = Math.max(0, Math.min(100, x));
    const clampedY = Math.max(0, Math.min(100, y));
    
    return { x: clampedX, y: clampedY };
  };

  // Get shine intensity based on rarity
  const getShineIntensity = (rarity: string) => {
    const rarityLower = rarity.toLowerCase();
    switch (rarityLower) {
      case 'common':
        return 0.33;
      case 'rare':
        return 0.60;
      case 'epic':
        return 0.85;
      case 'legendary':
        return 1.25;
      default:
        return 0.33;
    }
  };

  // Get gradient color based on rarity
  const getRarityGradient = (rarity: string) => {
    const rarityLower = rarity.toLowerCase();
    switch (rarityLower) {
      case 'common':
        return 'linear-gradient(45deg, #4A90E2, #7BB3F0)'; // Blue gradient
      case 'rare':
        return 'linear-gradient(45deg, #4CAF50, #81C784)'; // Green gradient
      case 'epic':
        return 'linear-gradient(45deg, #9C27B0, #BA68C8)'; // Purple gradient
      case 'legendary':
        return 'linear-gradient(45deg, #FFD700, #FFF176)'; // Gold gradient
      default:
        return 'linear-gradient(45deg, #4A90E2, #7BB3F0)'; // Default to blue
    }
  };

  const imageUrl = `data:image/png;base64,${image_b64}`;
  const shinePosition = getShinePosition();
  const shineIntensity = effectsEnabled ? getShineIntensity(rarity) : 0; // Hide rainbow when disabled

  const handleCardClick = () => {
    setEffectsEnabled(!effectsEnabled);
  };

  return (
    <div className="card" onClick={handleCardClick}>
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
          alt={`${modifier} ${base_name}`}
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
      <div className="card-info">
        <h3 
          className="card-name"
          style={{
            background: getRarityGradient(rarity),
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text'
          }}
        >
          {modifier} {base_name}
        </h3>
        <p className="card-rarity">{rarity}</p>
        <p className="card-id">#{id}</p>
      </div>
    </div>
  );
};

export default Card;
