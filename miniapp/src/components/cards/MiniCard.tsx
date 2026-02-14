import React, { memo } from 'react';
import BeatLoader from 'react-spinners/BeatLoader';
import type { CardData } from '@/types';

interface MiniCardProps {
  card: CardData;
  imageB64: string | null;
  isLoading: boolean;
  hasFailed: boolean;
  onClick: (card: CardData) => void;
}

const LockIndicator = () => (
  <div className="grid-card-lock-indicator">
    <svg className="grid-lock-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="white">
      <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zM9 6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9V6zm9 14H6V10h12v10zm-6-3c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2z"/>
    </svg>
  </div>
);

const MiniCard: React.FC<MiniCardProps> = ({ card, imageB64, isLoading, hasFailed, onClick }) => {
  const setName = card.rarity === 'Unique' ? 'UNIQUE' : (card.set_name || 'Unknown').toUpperCase();
  const hasImage = imageB64 && !hasFailed;

  const overlays = (
    <>
      {!card.locked && <div className="grid-card-number-overlay">#{card.id}</div>}
      <div className="grid-card-set-overlay">{setName}</div>
    </>
  );

  const cardInfo = (
    <div className="grid-card-info">
      <div className="grid-card-title">{card.modifier} {card.base_name}</div>
      <div className="grid-card-rarity">{card.rarity}</div>
    </div>
  );

  return (
    <div className="grid-card" onClick={() => onClick(card)}>
      {card.locked && <LockIndicator />}
      {hasImage ? (
        <>
          <img src={`data:image/png;base64,${imageB64}`} alt={card.base_name} decoding="async" />
          {overlays}
          {cardInfo}
        </>
      ) : (
        <div className="card-image-loader">
          {overlays}
          {hasFailed && <div className="grid-card-error"><div>❌</div></div>}
          {isLoading && !hasFailed && <BeatLoader color="#fff" size={6} speedMultiplier={0.8} />}
          {cardInfo}
        </div>
      )}
    </div>
  );
};

MiniCard.displayName = 'MiniCard';

export default memo(MiniCard, (prev, next) => (
  prev.card.id === next.card.id &&
  prev.card.locked === next.card.locked &&
  prev.imageB64 === next.imageB64 &&
  prev.isLoading === next.isLoading &&
  prev.hasFailed === next.hasFailed
));
