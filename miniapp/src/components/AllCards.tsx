import React, { memo } from 'react';
import MiniCard from './MiniCard';
import './AllCards.css';
import type { CardData } from '../types';
import { useBatchLoader } from '../hooks';

interface AllCardsProps {
  cards: CardData[];
  onCardClick: (card: CardData) => void;
  initData: string | null;
}

const AllCards: React.FC<AllCardsProps> = memo(({ cards, onCardClick, initData }) => {
  const { loadingCards, failedCards, registerCard } = useBatchLoader(cards, initData);

  return (
    <div className="all-cards-container">
      <div className="all-cards-grid">
        {cards.map((card) => (
          <MiniCard 
            key={card.id}
            card={card}
            onClick={onCardClick}
            isLoading={loadingCards.has(card.id)}
            hasFailed={failedCards.has(card.id)}
            registerCard={registerCard}
          />
        ))}
      </div>
    </div>
  );
});

AllCards.displayName = 'AllCards';

export default AllCards;
