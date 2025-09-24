import React from 'react';
import type { CardData, OrientationData } from '../types';
import Card from './Card';

interface CardModalProps {
  isOpen: boolean;
  card: CardData;
  orientation: OrientationData;
  orientationKey: number;
  authToken: string | null;
  onClose: () => void;
}

const CardModal: React.FC<CardModalProps> = ({
  isOpen,
  card,
  orientation,
  orientationKey,
  authToken,
  onClose
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
          authToken={authToken}
          shiny={true}
          showOwner={true}
        />
      </div>
    </div>
  );
};

export default CardModal;