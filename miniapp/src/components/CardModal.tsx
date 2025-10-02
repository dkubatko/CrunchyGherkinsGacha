import React from 'react';
import type { CardData, OrientationData } from '../types';
import Card from './Card';

interface CardModalProps {
  isOpen: boolean;
  card: CardData;
  orientation: OrientationData;
  orientationKey: number;
  initData: string | null;
  onClose: () => void;
  onShare?: (cardId: number) => Promise<void> | void;
  onCardOpen?: (card: Pick<CardData, 'id' | 'chat_id'>) => void;
}

const CardModal: React.FC<CardModalProps> = ({
  isOpen,
  card,
  orientation,
  orientationKey,
  initData,
  onClose,
  onShare,
  onCardOpen
}) => {
  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>×</button>
        <Card 
          {...card} 
          orientation={orientation}
          tiltKey={orientationKey}
          initData={initData}
          shiny={true}
          showOwner={true}
          onShare={onShare}
          showShareButton={false}
          onCardOpen={onCardOpen}
        />
      </div>
    </div>
  );
};

export default CardModal;