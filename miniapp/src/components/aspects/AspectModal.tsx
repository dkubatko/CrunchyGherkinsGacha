import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import type { AspectData, OrientationData } from '@/types';
import { ApiService } from '@/services/api';
import { getRarityGradient } from '@/utils/rarityStyles';
import { AnimatedImage } from '@/components/common';
import BeatLoader from 'react-spinners/BeatLoader';
import './AspectModal.css';

interface AspectModalProps {
  isOpen: boolean;
  aspect: AspectData;
  initData: string | null;
  onClose: () => void;
  isActionPanelVisible?: boolean;
  orientation: OrientationData;
  orientationKey: number;
}

const AspectModal: React.FC<AspectModalProps> = ({
  isOpen,
  aspect,
  initData,
  onClose,
  isActionPanelVisible = false,
  orientation,
  orientationKey,
}) => {
  const [fullImage, setFullImage] = useState<string | null>(null);
  const [imageLoading, setImageLoading] = useState(false);
  const [effectsEnabled, setEffectsEnabled] = useState(true);

  useEffect(() => {
    if (!isOpen || !initData) return;
    let cancelled = false;

    setFullImage(null);

    const loadImage = async () => {
      setImageLoading(true);
      try {
        const img = await ApiService.fetchAspectImage(aspect.id, initData);
        if (!cancelled) setFullImage(img);
      } catch {
        // thumbnail fallback handled by caller
      } finally {
        if (!cancelled) setImageLoading(false);
      }
    };

    void loadImage();
    return () => { cancelled = true; };
  }, [isOpen, aspect.id, initData]);

  if (!isOpen) return null;

  const setName = aspect.aspect_definition?.set_name ?? 'Unknown';
  const gradient = getRarityGradient(aspect.rarity);
  const imageUrl = fullImage ? `data:image/png;base64,${fullImage}` : '';

  return createPortal(
    <div className={`modal-overlay ${isActionPanelVisible ? 'with-action-panel' : ''}`} onClick={onClose}>
      <div className="modal-content aspect-modal-content" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="modal-close"
          onClick={onClose}
          aria-label="Close aspect"
          title="Close"
        >
          <span className="modal-close-icon" aria-hidden="true" />
        </button>

        {aspect.locked ? (
          <div className="aspect-modal-lock-indicator">
            <svg
              className="aspect-modal-lock-icon"
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="white"
            >
              <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zM9 6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9V6zm9 14H6V10h12v10zm-6-3c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2z"/>
            </svg>
            <span className="aspect-modal-lock-id">#{aspect.id}</span>
          </div>
        ) : (
          <div className="aspect-modal-id">#{aspect.id}</div>
        )}

        <div className="aspect-modal-shell">
          <div className="aspect-modal-sphere" onClick={() => setEffectsEnabled(e => !e)}>
            {fullImage ? (
              <AnimatedImage
                imageUrl={imageUrl}
                alt={aspect.display_name}
                rarity={aspect.rarity}
                orientation={orientation}
                effectsEnabled={effectsEnabled}
                tiltKey={orientationKey}
                borderRadius="25%"
                square
              />
            ) : imageLoading ? (
              <div className="aspect-modal-loader">
                <BeatLoader color="#fff" size={10} />
              </div>
            ) : (
              <div className="aspect-modal-placeholder">⬡</div>
            )}
          </div>

          <div className="aspect-modal-info">
            <h3
              className="aspect-modal-name"
              style={{
                background: gradient,
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
              }}
            >
              {aspect.display_name}
            </h3>
            <p className="aspect-modal-rarity">{aspect.rarity}</p>
            <p className="aspect-modal-set">{setName}</p>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default AspectModal;
