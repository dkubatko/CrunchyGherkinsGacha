import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import type { AspectData, OrientationData } from '@/types';
import { ApiService } from '@/services/api';
import { imageCache, aspectCacheId } from '@/lib/imageCache';
import { getRarityGradient } from '@/utils/rarityStyles';
import { AnimatedImage, ConfirmDialog } from '@/components/common';
import BeatLoader from 'react-spinners/BeatLoader';
import './AspectModal.css';

interface AspectModalProps {
  isOpen: boolean;
  aspect: AspectData;
  orientation: OrientationData;
  orientationKey: number;
  initData: string | null;
  onClose: () => void;
  onShare?: (aspectId: number) => Promise<void> | void;
  triggerBurn?: boolean;
  onBurnComplete?: () => void;
  isBurning?: boolean;
  isActionPanelVisible?: boolean;
}

const AspectModal: React.FC<AspectModalProps> = ({
  isOpen,
  aspect,
  orientation,
  orientationKey,
  initData,
  onClose,
  onShare,
  triggerBurn,
  onBurnComplete,
  isBurning = false,
  isActionPanelVisible = false,
}) => {
  const [fullImage, setFullImage] = useState<string | null>(null);
  const [imageLoading, setImageLoading] = useState(false);
  const [effectsEnabled, setEffectsEnabled] = useState(true);
  const [lockExpanded, setLockExpanded] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [showShareDialog, setShowShareDialog] = useState(false);
  const showInlineShareButton = Boolean(onShare);

  useEffect(() => {
    if (!isOpen || !initData) return;
    let cancelled = false;
    const cacheKey = aspectCacheId(aspect.id);

    const loadImage = async () => {
      // Check cache first (memory → IndexedDB)
      const cached = await imageCache.getAsync(cacheKey, 'full', null);
      if (cached) {
        if (!cancelled) {
          setFullImage(cached);
          setImageLoading(false);
        }
        return;
      }

      setImageLoading(true);
      try {
        const img = await ApiService.fetchAspectImage(aspect.id, initData);
        if (!cancelled) {
          setFullImage(img);
          imageCache.set(cacheKey, img, 'full', null);
        }
      } catch {
        // thumbnail fallback handled by caller
      } finally {
        if (!cancelled) setImageLoading(false);
      }
    };

    void loadImage();
    return () => { cancelled = true; };
  }, [isOpen, aspect.id, initData]);

  const handleShareClick = async (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (!onShare || sharing) return;
    setShowShareDialog(true);
  };

  const confirmShare = async () => {
    if (!onShare) return;
    try {
      setSharing(true);
      setShowShareDialog(false);
      await onShare(aspect.id);
    } catch (error) {
      console.error('Failed to share aspect:', error);
    } finally {
      setSharing(false);
    }
  };

  const cancelShare = () => {
    setShowShareDialog(false);
  };

  if (!isOpen) return null;

  const setName = aspect.aspect_definition?.set_name ?? 'Unknown';
  const gradient = getRarityGradient(aspect.rarity);
  const imageUrl = fullImage ? `data:image/png;base64,${fullImage}` : '';

  return createPortal(
    <div className={`modal-overlay ${isActionPanelVisible ? 'with-action-panel' : ''}`} onClick={isBurning ? undefined : onClose}>
      <div className="modal-content aspect-modal-content" onClick={(e) => e.stopPropagation()}>
        <ConfirmDialog
          isOpen={showShareDialog}
          onRequestClose={cancelShare}
          onConfirm={confirmShare}
          onCancel={cancelShare}
        >
          <p>Share to the group?</p>
        </ConfirmDialog>

        {!isBurning && (
          <button
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="Close aspect"
            title="Close"
          >
            <span className="modal-close-icon" aria-hidden="true" />
          </button>
        )}

        {aspect.locked ? (
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
            <span className="lock-id">#{aspect.id}</span>
          </div>
        ) : (
          <div className="card-id">#{aspect.id}</div>
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
                triggerBurn={triggerBurn}
                onBurnComplete={onBurnComplete}
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
            <div className="aspect-name-row">
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
              {showInlineShareButton && (
                <button
                  className="aspect-share-button-inline"
                  onClick={handleShareClick}
                  disabled={sharing}
                  aria-label="Share aspect"
                >
                  {sharing ? (
                    <BeatLoader color="rgba(255, 255, 255, 0.8)" size={4} speedMultiplier={0.8} />
                  ) : (
                    <svg 
                      className="share-icon-inline"
                      xmlns="http://www.w3.org/2000/svg"  
                      viewBox="0 0 50 50"
                      fill="currentColor"
                    >
                      <path d="M46.137,6.552c-0.75-0.636-1.928-0.727-3.146-0.238l-0.002,0C41.708,6.828,6.728,21.832,5.304,22.445c-0.259,0.09-2.521,0.934-2.288,2.814c0.208,1.695,2.026,2.397,2.248,2.478l8.893,3.045c0.59,1.964,2.765,9.21,3.246,10.758c0.3,0.965,0.789,2.233,1.646,2.494c0.752,0.29,1.5,0.025,1.984-0.355l5.437-5.043l8.777,6.845l0.209,0.125c0.596,0.264,1.167,0.396,1.712,0.396c0.421,0,0.825-0.079,1.211-0.237c1.315-0.54,1.841-1.793,1.896-1.935l6.556-34.077C47.231,7.933,46.675,7.007,46.137,6.552z M22,32l-3,8l-3-10l23-17L22,32z"/>
                    </svg>
                  )}
                </button>
              )}
            </div>
            <p className="aspect-modal-rarity">{aspect.rarity}</p>
            <p className="aspect-modal-set">{setName}</p>
            {aspect.owner && (
              <p className="aspect-modal-owner">
                Owned by <span className="aspect-modal-owner-username">@{aspect.owner}</span>
              </p>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default AspectModal;
