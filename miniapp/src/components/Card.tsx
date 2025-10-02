import React, { useState, useEffect } from 'react';
import ShinyImage from './ShinyImage';
import { imageCache } from '../lib/imageCache';
import { getRarityGradient } from '../utils/rarityStyles';
import type { OrientationData } from '../types';

const inFlightFullImageRequests = new Map<number, Promise<string>>();

interface CardProps {
  rarity: string;
  modifier: string;
  base_name: string;
  orientation: OrientationData;
  tiltKey: number;
  id: number;
  initData: string | null;
  shiny: boolean;
  owner?: string;
  showOwner?: boolean;
  onShare?: (cardId: number) => Promise<void> | void;
  showShareButton?: boolean;
  locked?: boolean;
}

const Card: React.FC<CardProps> = ({
  rarity,
  modifier,
  base_name,
  orientation,
  tiltKey,
  id,
  initData,
  shiny,
  owner,
  showOwner = false,
  onShare,
  showShareButton = false,
  locked = false
}) => {
  const [imageB64, setImageB64] = useState<string | null>(null);
  const [loadingImage, setLoadingImage] = useState(true);
  const [effectsEnabled, setEffectsEnabled] = useState(true);
  const [sharing, setSharing] = useState(false);
  const [showShareDialog, setShowShareDialog] = useState(false);

  useEffect(() => {
    const fetchImage = async () => {
      if (!id || !initData) return;

      if (imageCache.has(id, 'full')) {
        setImageB64(imageCache.get(id, 'full')!);
        setLoadingImage(false);
        return;
      }

      setLoadingImage(true);
      try {
        let imageRequest = inFlightFullImageRequests.get(id);
        if (!imageRequest) {
          imageRequest = (async () => {
            const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com';
            const response = await fetch(`${apiBaseUrl}/cards/image/${id}`, {
              headers: {
                'Authorization': `tma ${initData}`
              }
            });

            if (!response.ok) {
              throw new Error('Failed to fetch image');
            }

            const imageData = await response.json();
            imageCache.set(id, imageData, 'full');
            return imageData;
          })()
            .finally(() => {
              inFlightFullImageRequests.delete(id);
            });

          inFlightFullImageRequests.set(id, imageRequest);
        }

        const imageData = await imageRequest;
        setImageB64(imageData);
      } catch (error) {
        console.error("Error fetching card image:", error);
      } finally {
        setLoadingImage(false);
      }
    };

    fetchImage();
  }, [id, initData]);

  const imageUrl = imageB64 ? `data:image/png;base64,${imageB64}` : '';

  const handleCardClick = () => {
    setEffectsEnabled(!effectsEnabled);
  };

  const handleShareClick = async (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (!onShare || sharing) {
      return;
    }
    setShowShareDialog(true);
  };

  const confirmShare = async () => {
    if (!onShare) return;
    
    try {
      setSharing(true);
      setShowShareDialog(false);
      await onShare(id);
    } catch (error) {
      console.error('Failed to share card:', error);
    } finally {
      setSharing(false);
    }
  };

  const cancelShare = () => {
    setShowShareDialog(false);
  };

  return (
    <div className="card" onClick={handleCardClick}>
      {showShareDialog && (
        <div 
          className="share-dialog-overlay" 
          onClick={(e) => {
            e.stopPropagation();
            setShowShareDialog(false);
          }}
        >
          <div 
            className="share-dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <p>Share to the group?</p>
            <div className="share-dialog-buttons">
              <button onClick={confirmShare} className="share-confirm-btn">Yes</button>
              <button onClick={cancelShare} className="share-cancel-btn">No</button>
            </div>
          </div>
        </div>
      )}
      {locked && (
        <div className="card-lock-indicator">
          <svg
            className="lock-icon"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="white"
          >
            <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zM9 6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9V6zm9 14H6V10h12v10zm-6-3c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2z"/>
          </svg>
        </div>
      )}
      {showShareButton && onShare && (
        <button
          className="card-share-button"
          onClick={handleShareClick}
          disabled={sharing}
          aria-label="Share card"
        >
          {sharing ? (
            <div className="share-spinner"></div>
          ) : (
            <svg 
              className="share-icon"
              xmlns="http://www.w3.org/2000/svg"  
              viewBox="0 0 50 50"
              fill="white"
            >
              <path d="M46.137,6.552c-0.75-0.636-1.928-0.727-3.146-0.238l-0.002,0C41.708,6.828,6.728,21.832,5.304,22.445	c-0.259,0.09-2.521,0.934-2.288,2.814c0.208,1.695,2.026,2.397,2.248,2.478l8.893,3.045c0.59,1.964,2.765,9.21,3.246,10.758	c0.3,0.965,0.789,2.233,1.646,2.494c0.752,0.29,1.5,0.025,1.984-0.355l5.437-5.043l8.777,6.845l0.209,0.125	c0.596,0.264,1.167,0.396,1.712,0.396c0.421,0,0.825-0.079,1.211-0.237c1.315-0.54,1.841-1.793,1.896-1.935l6.556-34.077	C47.231,7.933,46.675,7.007,46.137,6.552z M22,32l-3,8l-3-10l23-17L22,32z"/>
            </svg>
          )}
        </button>
      )}
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

