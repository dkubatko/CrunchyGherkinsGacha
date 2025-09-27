import React, { useEffect, useState } from 'react';
import Card from './Card';
import { ApiService } from '../services/api';
import { imageCache } from '../lib/imageCache';
import type { OrientationData, CardData } from '../types';

interface SingleCardViewProps {
  cardId: number;
  initData: string;
  orientation: OrientationData;
  orientationKey: number;
}

// Fetches card metadata minimally by reusing batch endpoints if necessary in future.
// Currently we only need the image, but Card component requires some textual fields.
// We'll display placeholder metadata while focusing on image rendering.
export const SingleCardView: React.FC<SingleCardViewProps> = ({ cardId, initData, orientation, orientationKey }) => {
  const [imageLoaded, setImageLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cardData, setCardData] = useState<CardData | null>(null);
  // Image data is cached by Card component; we only trigger fetch/store via ApiService for preloading.

  useEffect(() => {
    let isMounted = true;
    setImageLoaded(false);
    setError(null);

    const loadImage = async () => {
      try {
        if (imageCache.has(cardId, 'full')) {
          if (isMounted) {
            setImageLoaded(true);
          }
          return;
        }
        const b64 = await ApiService.fetchCardImage(cardId, initData);
        imageCache.set(cardId, b64, 'full');
        if (isMounted) {
          setImageLoaded(true);
        }
      } catch (e) {
        console.error('Failed to load single card image', e);
        const message = e instanceof Error ? e.message : 'Failed to load image';
        if (isMounted) {
          setError(message);
        }
      }
    };
    loadImage();
    return () => {
      isMounted = false;
    };
  }, [cardId, initData]);

  useEffect(() => {
    let isMounted = true;
    setCardData(null);

    const loadMetadata = async () => {
      try {
        const detail = await ApiService.fetchCardDetails(cardId, initData);
        if (isMounted) {
          setCardData(detail);
        }
      } catch (e) {
        console.error('Failed to load card metadata', e);
        const message = e instanceof Error ? e.message : 'Failed to load card details';
        if (isMounted) {
          setError(message);
        }
      }
    };

    loadMetadata();

    return () => {
      isMounted = false;
    };
  }, [cardId, initData]);

  if (error) {
    return (
      <div className="single-card-layout">
        <h1>Error: {error}</h1>
      </div>
    );
  }
  if (!imageLoaded || !cardData) {
    return (
      <div className="single-card-layout">
        <h1>Loading...</h1>
      </div>
    );
  }

  // Use Card component for consistency; provide minimal fake metadata (rarity placeholder)
  return (
    <div className="single-card-layout">
      <div className="card-container single-card">
        <Card
          id={cardId}
          rarity={cardData.rarity}
          modifier={cardData.modifier}
          base_name={cardData.base_name}
          orientation={orientation}
          tiltKey={orientationKey}
          initData={initData}
          shiny={true}
          showOwner={true}
          owner={cardData.owner}
        />
      </div>
    </div>
  );
};

export default SingleCardView;
