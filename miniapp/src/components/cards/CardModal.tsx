import React from 'react';
import { createPortal } from 'react-dom';
import type { CardData, OrientationData } from '@/types';
import Card from './Card';
import './CardModal.css';

interface CardModalProps {
  isOpen: boolean;
  card: CardData;
  orientation: OrientationData;
  orientationKey: number;
  initData: string | null;
  onClose: () => void;
  onShare?: (cardId: number) => Promise<void> | void;
  onCardOpen?: (card: Pick<CardData, 'id' | 'chat_id'>) => void;
  triggerBurn?: boolean;
  onBurnComplete?: () => void;
  isBurning?: boolean;
  isActionPanelVisible?: boolean;
  enableDownload?: boolean;
}

const CardModal: React.FC<CardModalProps> = ({
  isOpen,
  card,
  orientation,
  orientationKey,
  initData,
  onClose,
  onShare,
  onCardOpen,
  triggerBurn,
  onBurnComplete,
  isBurning = false,
  isActionPanelVisible = false,
  enableDownload = true
}) => {
  if (!isOpen) return null;

  return createPortal(
    <div className={`modal-overlay ${isActionPanelVisible ? 'with-action-panel' : ''}`} onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        {!isBurning && (
          <button
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="Close card"
            title="Close"
          >
            <span className="modal-close-icon" aria-hidden="true" />
          </button>
        )}
        <div className="modal-card-shell">
          <Card 
            {...card} 
            orientation={orientation}
            tiltKey={orientationKey}
            initData={initData}
            shiny={true}
            showOwner={true}
            onShare={onShare}
            showShareButton={Boolean(onShare)}
            onCardOpen={onCardOpen}
            triggerBurn={triggerBurn}
            onBurnComplete={onBurnComplete}
            enableDownload={enableDownload}
          />
        </div>
      </div>
    </div>,
    document.body
  );
};

export default CardModal;