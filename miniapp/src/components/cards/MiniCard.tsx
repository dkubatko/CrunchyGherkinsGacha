import React, { useState, useEffect, memo, useRef } from 'react';
import { useInView } from 'react-intersection-observer';
import { imageCache } from '@/lib/imageCache';
import type { CardData } from '@/types';

interface MiniCardProps {
  card: CardData;
  initData?: string | null;
  onClick: (card: CardData) => void;
  isLoading?: boolean;
  hasFailed?: boolean;
  setCardVisible: (cardId: number, isVisible: boolean) => void;
}

const MiniCard: React.FC<MiniCardProps> = ({ card, onClick, isLoading = false, hasFailed = false, setCardVisible }) => {
  const imageUpdatedAt = card.image_updated_at ?? null;
  const cachedImage = imageCache.has(card.id, 'thumb') ? imageCache.get(card.id, 'thumb') : null;
  const [imageB64, setImageB64] = useState<string | null>(cachedImage);
  const [loadState, setLoadState] = useState<'idle' | 'loading-cache' | 'waiting-server' | 'done'>(
    cachedImage ? 'done' : 'idle'
  );
  const isMounted = useRef(true);

  useEffect(() => {
    isMounted.current = true;
    return () => { isMounted.current = false; };
  }, []);

  const { ref, inView } = useInView({
    threshold: 0,
    rootMargin: '600px',
    triggerOnce: false,
  });

  // When visible and idle: try cache → if miss, request from server
  useEffect(() => {
    if (imageB64 || loadState !== 'idle' || !inView) return;
    
    const loadImage = async () => {
      setLoadState('loading-cache');
      try {
        const cached = await imageCache.getAsync(card.id, 'thumb', imageUpdatedAt);
        if (!isMounted.current) return;
        if (cached) {
          setImageB64(cached);
          setLoadState('done');
          return;
        }
      } catch {
        if (!isMounted.current) return;
      }
      setLoadState('waiting-server');
    };
    void loadImage();
  }, [card.id, imageB64, inView, imageUpdatedAt, loadState]);

  // Notify batch loader only when server fetch needed
  useEffect(() => {
    if (loadState === 'waiting-server') {
      setCardVisible(card.id, inView);
    } else if (loadState === 'done' || loadState === 'loading-cache') {
      setCardVisible(card.id, false);
    }
  }, [card.id, inView, loadState, setCardVisible]);

  // Check cache when batch loader finishes (isLoading: true → false triggers re-run)
  useEffect(() => {
    if (imageB64 || loadState !== 'waiting-server') return;
    
    const cached = imageCache.get(card.id, 'thumb');
    if (cached) {
      setImageB64(cached);
      setLoadState('done');
    }
  }, [card.id, isLoading, imageB64, loadState]);

  const showImage = imageB64 && !hasFailed;
  const showLoading = !imageB64 && (isLoading || loadState === 'loading-cache') && !hasFailed;
  const showError = hasFailed;

  return (
    <div className="grid-card" ref={ref} onClick={() => onClick(card)}>
      {card.locked ? (
        <div className="grid-card-lock-indicator">
          <svg
            className="grid-lock-icon"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="white"
          >
            <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zM9 6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9V6zm9 14H6V10h12v10zm-6-3c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2z"/>
          </svg>
        </div>
      ) : null}
      {showImage ? (
        <>
          <img src={`data:image/png;base64,${imageB64}`} alt={`${card.rarity} ${card.modifier} ${card.base_name}`} loading="lazy" />
          {!card.locked && <div className="grid-card-number-overlay">#{card.id}</div>}
          <div className="grid-card-set-overlay">{card.rarity === 'Unique' ? 'UNIQUE' : (card.set_name || 'Unknown').toUpperCase()}</div>
          <div className="grid-card-info">
            <div className="grid-card-title">{card.modifier} {card.base_name}</div>
            <div className="grid-card-rarity">{card.rarity}</div>
          </div>
        </>
      ) : showError ? (
        <div className="card-image-loader">
          {!card.locked && <div className="grid-card-number-overlay">#{card.id}</div>}
          <div className="grid-card-set-overlay">{card.rarity === 'Unique' ? 'UNIQUE' : (card.set_name || 'Unknown').toUpperCase()}</div>
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
          {!card.locked && <div className="grid-card-number-overlay">#{card.id}</div>}
          <div className="grid-card-set-overlay">{card.rarity === 'Unique' ? 'UNIQUE' : (card.set_name || 'Unknown').toUpperCase()}</div>
          <div className="spinner-mini"></div>
          <div className="grid-card-info">
            <div className="grid-card-title">{card.modifier} {card.base_name}</div>
            <div className="grid-card-rarity">{card.rarity}</div>
          </div>
        </div>
      ) : (
        <div className="card-image-loader">
          {!card.locked && <div className="grid-card-number-overlay">#{card.id}</div>}
          <div className="grid-card-set-overlay">{card.rarity === 'Unique' ? 'UNIQUE' : (card.set_name || 'Unknown').toUpperCase()}</div>
          <div className="grid-card-info">
            <div className="grid-card-title">{card.modifier} {card.base_name}</div>
            <div className="grid-card-rarity">{card.rarity}</div>
          </div>
        </div>
      )}
    </div>
  );
};

MiniCard.displayName = 'MiniCard';

// Custom comparison function to prevent unnecessary re-renders
const arePropsEqual = (prevProps: MiniCardProps, nextProps: MiniCardProps) => {
  return (
    prevProps.card.id === nextProps.card.id &&
    prevProps.card.image_updated_at === nextProps.card.image_updated_at &&
    prevProps.isLoading === nextProps.isLoading &&
    prevProps.hasFailed === nextProps.hasFailed &&
    prevProps.onClick === nextProps.onClick &&
    prevProps.setCardVisible === nextProps.setCardVisible
  );
};

export default memo(MiniCard, arePropsEqual);
