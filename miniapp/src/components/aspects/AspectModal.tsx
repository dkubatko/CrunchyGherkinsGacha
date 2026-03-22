import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import type { AspectData } from '@/types';
import { ApiService } from '@/services/api';
import { getRarityGradient } from '@/utils/rarityStyles';
import BeatLoader from 'react-spinners/BeatLoader';
import './AspectModal.css';

interface AspectModalProps {
  isOpen: boolean;
  aspect: AspectData;
  initData: string | null;
  onClose: () => void;
  isActionPanelVisible?: boolean;
}

const AspectModal: React.FC<AspectModalProps> = ({
  isOpen,
  aspect,
  initData,
  onClose,
  isActionPanelVisible = false,
}) => {
  const [fullImage, setFullImage] = useState<string | null>(null);
  const [imageLoading, setImageLoading] = useState(false);

  useEffect(() => {
    if (!isOpen || !initData) return;
    let cancelled = false;

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

        <div className="aspect-modal-sphere">
          {fullImage ? (
            <img
              src={`data:image/png;base64,${fullImage}`}
              alt={aspect.display_name}
              className="aspect-modal-image"
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
          <h2 className="aspect-modal-name">{aspect.display_name}</h2>
          <div
            className="aspect-modal-rarity"
            style={{ background: gradient, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
          >
            {aspect.rarity}
          </div>
          <div className="aspect-modal-set">Set: {setName}</div>
          {aspect.locked && <div className="aspect-modal-locked">🔒 Locked</div>}
          <div className="aspect-modal-id">#{aspect.id}</div>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default AspectModal;
