import React, { memo } from 'react';
import BeatLoader from 'react-spinners/BeatLoader';
import type { AspectData } from '@/types';

interface MiniAspectProps {
  aspect: AspectData;
  imageB64: string | null;
  isLoading: boolean;
  hasFailed: boolean;
  onClick: (aspect: AspectData) => void;
}

const LockIndicator = () => (
  <div className="grid-card-lock-indicator">
    <svg className="grid-lock-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="white">
      <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zM9 6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9V6zm9 14H6V10h12v10zm-6-3c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2z"/>
    </svg>
  </div>
);

const MiniAspect: React.FC<MiniAspectProps> = ({ aspect, imageB64, isLoading, hasFailed, onClick }) => {
  const setName = aspect.aspect_definition?.set_name
    ? aspect.aspect_definition.set_name.toUpperCase()
    : 'ASPECT';
  const hasImage = imageB64 && !hasFailed;

  const overlays = (
    <>
      {!aspect.locked && <div className="grid-card-number-overlay">#{aspect.id}</div>}
      <div className="grid-card-set-overlay">{setName}</div>
    </>
  );

  const cardInfo = (
    <div className="grid-card-info">
      <div className="grid-card-title">{aspect.display_name}</div>
      <div className="grid-card-rarity">{aspect.rarity}</div>
    </div>
  );

  return (
    <div className="grid-card aspect-sphere" onClick={() => onClick(aspect)}>
      {aspect.locked && <LockIndicator />}
      {hasImage ? (
        <>
          <img src={`data:image/png;base64,${imageB64}`} alt={aspect.display_name} decoding="async" />
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

MiniAspect.displayName = 'MiniAspect';

export default memo(MiniAspect, (prev, next) => (
  prev.aspect.id === next.aspect.id &&
  prev.aspect.locked === next.aspect.locked &&
  prev.imageB64 === next.imageB64 &&
  prev.isLoading === next.isLoading &&
  prev.hasFailed === next.hasFailed
));
