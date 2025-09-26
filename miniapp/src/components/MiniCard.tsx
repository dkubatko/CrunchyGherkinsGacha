import React, { useState, useEffect, memo } from 'react';
import { useInView } from 'react-intersection-observer';
import { imageCache } from '../lib/imageCache';
import type { CardData } from '../types';

interface MiniCardProps {
  card: CardData;
  initData?: string | null;
  onClick: (card: CardData) => void;
  isLoading?: boolean;
  hasFailed?: boolean;
  setCardVisible: (cardId: number, isVisible: boolean) => void;
}

const MiniCard: React.FC<MiniCardProps> = memo(({ card, onClick, isLoading = false, hasFailed = false, setCardVisible }) => {
  // Check if we have cached data immediately to set initial state
  const cachedImage = imageCache.has(card.id) ? imageCache.get(card.id) : null;
  const [imageB64, setImageB64] = useState<string | null>(cachedImage);

  // Use react-intersection-observer for reliable visibility detection
  const { ref, inView } = useInView({
    threshold: 0.1,
    rootMargin: '300px', // Load images 300px before they become visible
    triggerOnce: false, // Keep monitoring visibility changes
  });

  // Notify parent when visibility changes
  useEffect(() => {
    setCardVisible(card.id, inView);
  }, [card.id, inView, setCardVisible]);

  // Effect to check cache when loading state changes or periodically
  useEffect(() => {
    if (imageB64) return; // Already have image, no need to check
    
    if (imageCache.has(card.id)) {
      const cached = imageCache.get(card.id);
      if (cached) {
        setImageB64(cached);
        return;
      }
    }

    // If we're loading, check cache periodically
    if (isLoading) {
      const interval = setInterval(() => {
        if (imageCache.has(card.id)) {
          const cached = imageCache.get(card.id);
          if (cached) {
            setImageB64(cached);
            clearInterval(interval);
          }
        }
      }, 100);

      return () => clearInterval(interval);
    }
  }, [card.id, isLoading, imageB64]);

  const showImage = imageB64 && !hasFailed;
  const showLoading = !imageB64 && isLoading && !hasFailed;
  const showError = hasFailed;

  return (
    <div className="grid-card" ref={ref} onClick={() => onClick(card)}>
      {showImage ? (
        <>
          <img src={`data:image/png;base64,${imageB64}`} alt={`${card.rarity} ${card.modifier} ${card.base_name}`} loading="lazy" />
          <div className="grid-card-info">
            <div className="grid-card-title">{card.modifier} {card.base_name}</div>
            <div className="grid-card-rarity">{card.rarity}</div>
          </div>
        </>
      ) : showError ? (
        <div className="card-image-loader">
          <div className="grid-card-error">
            <div>❌</div>
            <div className="grid-card-info">
              <div className="grid-card-title">{card.modifier} {card.base_name}</div>
              <div className="grid-card-rarity">{card.rarity}</div>
            </div>
          </div>
        </div>
      ) : showLoading ? (
        <div className="card-image-loader">
          <div className="spinner-mini"></div>
          <div className="grid-card-info">
            <div className="grid-card-title">{card.modifier} {card.base_name}</div>
            <div className="grid-card-rarity">{card.rarity}</div>
          </div>
        </div>
      ) : (
        <div className="card-image-loader">
          <div className="grid-card-info">
            <div className="grid-card-title">{card.modifier} {card.base_name}</div>
            <div className="grid-card-rarity">{card.rarity}</div>
          </div>
        </div>
      )}
    </div>
  );
});

MiniCard.displayName = 'MiniCard';

export default MiniCard;
