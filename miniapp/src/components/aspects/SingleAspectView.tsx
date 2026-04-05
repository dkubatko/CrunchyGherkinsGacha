import React, { useEffect, useState } from 'react';
import { Title } from '@/components/common';
import { AnimatedImage } from '@/components/common';
import { ApiService } from '@/services/api';
import { imageCache, aspectCacheId } from '@/lib/imageCache';
import { getRarityGradient } from '@/utils/rarityStyles';
import type { OrientationData, AspectData } from '@/types';
import './SingleAspectView.css';

interface SingleAspectViewProps {
  aspectId: number;
  initData: string;
  orientation: OrientationData;
  orientationKey: number;
}

export const SingleAspectView: React.FC<SingleAspectViewProps> = ({ aspectId, initData, orientation, orientationKey }) => {
  const [aspectData, setAspectData] = useState<AspectData | null>(null);
  const [fullImage, setFullImage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [effectsEnabled, setEffectsEnabled] = useState(true);
  const [lockExpanded, setLockExpanded] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const load = async () => {
      try {
        const detail = await ApiService.fetchAspectDetail(aspectId, initData);
        if (isMounted) setAspectData(detail);
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Failed to load aspect details';
        if (isMounted) setError(msg);
      }
    };
    load();
    return () => { isMounted = false; };
  }, [aspectId, initData]);

  useEffect(() => {
    let isMounted = true;
    const cacheKey = aspectCacheId(aspectId);
    const load = async () => {
      // Check cache first
      const cached = await imageCache.getAsync(cacheKey, 'full', null);
      if (cached) {
        if (isMounted) setFullImage(cached);
        return;
      }
      try {
        const img = await ApiService.fetchAspectImage(aspectId, initData);
        if (isMounted) {
          setFullImage(img);
          imageCache.set(cacheKey, img, 'full', null);
        }
      } catch (e) {
        console.error('Failed to load aspect image', e);
        if (isMounted) setError(e instanceof Error ? e.message : 'Failed to load image');
      }
    };
    load();
    return () => { isMounted = false; };
  }, [aspectId, initData]);

  if (error) {
    return (
      <div className="single-aspect-layout">
        <Title title={`Error: ${error}`} />
      </div>
    );
  }
  if (!aspectData || !fullImage) {
    return (
      <div className="single-aspect-layout">
        <Title title="Loading..." loading />
      </div>
    );
  }

  const setName = aspectData.aspect_definition?.set_name ?? 'Unknown';
  const gradient = getRarityGradient(aspectData.rarity);
  const imageUrl = `data:image/png;base64,${fullImage}`;

  return (
    <div className="single-aspect-layout">
      <div className="single-aspect-card">
        {aspectData.locked ? (
          <div
            className={`card-lock-indicator ${lockExpanded ? 'expanded' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              setLockExpanded(!lockExpanded);
            }}
            onMouseEnter={() => {
              if (window.matchMedia('(hover: hover)').matches) setLockExpanded(true);
            }}
            onMouseLeave={() => {
              if (window.matchMedia('(hover: hover)').matches) setLockExpanded(false);
            }}
          >
            <svg
              className="lock-icon"
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="white"
            >
              <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zM9 6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9V6zm9 14H6V10h12v10zm-6-3c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2z"/>
            </svg>
            <span className="lock-id">#{aspectData.id}</span>
          </div>
        ) : (
          <div className="card-id">#{aspectData.id}</div>
        )}
        <div className="single-aspect-sphere" onClick={() => setEffectsEnabled(e => !e)}>
          <AnimatedImage
            imageUrl={imageUrl}
            alt={aspectData.display_name}
            rarity={aspectData.rarity}
            orientation={orientation}
            effectsEnabled={effectsEnabled}
            tiltKey={orientationKey}
            borderRadius="25%"
            square
          />
        </div>
        <div className="single-aspect-info">
          <h2
            className="single-aspect-name"
            style={{
              background: gradient,
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            {aspectData.display_name}
          </h2>
          <p className="single-aspect-rarity">{aspectData.rarity}</p>
          <span className="single-aspect-set">{setName.toUpperCase()}</span>
          {aspectData.owner && (
            <p className="single-aspect-owner">Owned by <span className="single-aspect-owner-username">@{aspectData.owner}</span></p>
          )}
        </div>
      </div>
    </div>
  );
};

export default SingleAspectView;
