import React, { useState, useEffect, memo, useRef } from 'react';
import { imageCache } from '../lib/imageCache';
import type { CardData } from '../types';

interface MiniCardProps {
  card: CardData;
  initData?: string | null;
  onClick: (card: CardData) => void;
  isLoading?: boolean;
  hasFailed?: boolean;
  registerCard?: (cardId: number, element: Element | null) => void;
}

const MiniCard: React.FC<MiniCardProps> = memo(({ card, onClick, isLoading = false, hasFailed = false, registerCard }) => {
  // Check if we have cached data immediately to set initial state
  const cachedImage = imageCache.has(card.id) ? imageCache.get(card.id) : null;
  const [imageB64, setImageB64] = useState<string | null>(cachedImage);
  const cardRef = useRef<HTMLDivElement>(null);

  // Register this card element with the intersection observer
  useEffect(() => {
    if (registerCard && cardRef.current) {
      registerCard(card.id, cardRef.current);
    }
    
    return () => {
      if (registerCard) {
        registerCard(card.id, null);
      }
    };
  }, [card.id, registerCard]);

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
    <div className="grid-card" ref={cardRef} onClick={() => onClick(card)}>
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
