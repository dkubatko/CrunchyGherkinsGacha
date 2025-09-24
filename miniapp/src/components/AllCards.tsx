import React, { memo } from 'react';
import MiniCard from './MiniCard';
import './AllCards.css';
import type { CardData } from '../types';

interface AllCardsProps {
  cards: CardData[];
  onCardClick: (card: CardData) => void;
  initData: string | null;
}

const AllCards: React.FC<AllCardsProps> = memo(({ cards, onCardClick, initData }) => {
  return (
    <div className="all-cards-grid">
      {cards.map((card) => (
        <MiniCard 
          key={card.id}
          card={card}
          initData={initData}
          onClick={onCardClick}
        />
      ))}
    </div>
  );
});

AllCards.displayName = 'AllCards';

export default AllCards;
