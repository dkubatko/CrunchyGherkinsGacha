import React, { useEffect, useState } from 'react';
import { Title } from '@/components/common';
import { AnimatedImage } from '@/components/common';
import { ApiService } from '@/services/api';
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
    const load = async () => {
      try {
        const img = await ApiService.fetchAspectImage(aspectId, initData);
        if (isMounted) setFullImage(img);
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
          <div className="card-id">🔒 #{aspectData.id}</div>
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
            <p className="single-aspect-owner">Owned by @{aspectData.owner}</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default SingleAspectView;
