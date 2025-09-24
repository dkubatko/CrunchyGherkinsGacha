import React, { useState, useEffect, memo } from 'react';
import { imageCache } from '../lib/imageCache';
import type { CardData } from '../types';

interface MiniCardProps {
  card: CardData;
  initData: string | null;
  onClick: (card: CardData) => void;
}

const MiniCard: React.FC<MiniCardProps> = memo(({ card, initData, onClick }) => {
  // Check if we have cached data immediately to set initial state
  const cachedImage = imageCache.has(card.id) ? imageCache.get(card.id) : null;
  
  const [imageB64, setImageB64] = useState<string | null>(cachedImage);
  const [loading, setLoading] = useState(!cachedImage);
  const [error, setError] = useState(false);

  useEffect(() => {
    const fetchImage = async () => {
      if (!initData || !card.id) return;

      if (imageCache.has(card.id)) {
        setImageB64(imageCache.get(card.id)!);
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(false);
        const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com';
        const response = await fetch(`${apiBaseUrl}/cards/image/${card.id}`, {
          headers: {
            'Authorization': `tma ${initData}`
          }
        });
        if (!response.ok) {
          throw new Error('Failed to fetch image');
        }
        const imageData = await response.json();
        imageCache.set(card.id, imageData);
        setImageB64(imageData);
        setLoading(false);
      } catch (err) {
        console.error(`Error fetching image for card ${card.id}:`, err);
        setError(true);
        setLoading(false);
      }
    };

    fetchImage();
  }, [card.id, initData]);

  return (
    <div className="grid-card" onClick={() => onClick(card)}>
      {imageB64 && !loading && !error ? (
        <>
          <img src={`data:image/png;base64,${imageB64}`} alt={`${card.rarity} ${card.modifier} ${card.base_name}`} loading="lazy" />
          <div className="grid-card-info">
            <div className="grid-card-title">{card.modifier} {card.base_name}</div>
            <div className="grid-card-rarity">{card.rarity}</div>
          </div>
        </>
      ) : error ? (
        <div className="card-image-loader">
          <div className="grid-card-error">
            <div>❌</div>
            <div className="grid-card-info">
              <div className="grid-card-title">{card.modifier} {card.base_name}</div>
              <div className="grid-card-rarity">{card.rarity}</div>
            </div>
          </div>
        </div>
      ) : (
        <div className="card-image-loader">
          <div className="spinner-mini"></div>
        </div>
      )}
    </div>
  );
});

MiniCard.displayName = 'MiniCard';

export default MiniCard;
