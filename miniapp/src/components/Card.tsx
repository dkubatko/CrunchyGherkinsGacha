import React, { useState, useEffect } from 'react';
import ShinyImage from './ShinyImage';
import { imageCache } from '../lib/imageCache';
import type { OrientationData } from '../types';

interface CardProps {
  rarity: string;
  modifier: string;
  base_name: string;
  orientation: OrientationData;
  tiltKey: number;
  id: number;
  authToken: string | null;
  shiny: boolean;
  owner?: string;
  showOwner?: boolean;
}

const Card: React.FC<CardProps> = ({ rarity, modifier, base_name, orientation, tiltKey, id, authToken, shiny, owner, showOwner = false }) => {
  const [imageB64, setImageB64] = useState<string | null>(null);
  const [loadingImage, setLoadingImage] = useState(true);
  const [effectsEnabled, setEffectsEnabled] = useState(true);

  useEffect(() => {
    const fetchImage = async () => {
      if (!id || !authToken) return;

      if (imageCache.has(id)) {
        setImageB64(imageCache.get(id)!);
        setLoadingImage(false);
        return;
      }

      setLoadingImage(true);
      try {
        const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com';
        const response = await fetch(`${apiBaseUrl}/cards/image/${id}`, {
          headers: {
            'Authorization': `Bearer ${authToken}`
          }
        });
        if (!response.ok) {
          throw new Error('Failed to fetch image');
        }
        const imageData = await response.json();
        imageCache.set(id, imageData);
        setImageB64(imageData);
      } catch (error) {
        console.error("Error fetching card image:", error);
      } finally {
        setLoadingImage(false);
      }
    };

    fetchImage();
  }, [id, authToken]);

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

  const imageUrl = imageB64 ? `data:image/png;base64,${imageB64}` : '';

  const handleCardClick = () => {
    setEffectsEnabled(!effectsEnabled);
  };

  return (
    <div className="card" onClick={handleCardClick}>
      {loadingImage ? (
        <div className="card-image-container">
          <div className="spinner"></div>
        </div>
      ) : (
        shiny ? (
          <ShinyImage 
            imageUrl={imageUrl}
            alt={`${modifier} ${base_name}`}
            rarity={rarity}
            orientation={orientation}
            effectsEnabled={effectsEnabled}
            tiltKey={tiltKey}
          />
        ) : (
          <div className="card-image-container">
            <img 
              src={imageUrl} 
              alt={`${modifier} ${base_name}`}
            />
          </div>
        )
      )}
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
        {showOwner && owner && (
          <p className="card-owner">
            Owned by <span className="card-owner-username">@{owner}</span>
          </p>
        )}
      </div>
    </div>
  );
};

export default Card;

