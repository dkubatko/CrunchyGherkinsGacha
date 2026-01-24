import React, { memo, useCallback, useRef, useEffect } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import MiniCard from './MiniCard';
import { useVirtualizedImages } from '@/hooks';
import './AllCards.css';
import type { CardData } from '@/types';

interface AllCardsProps {
  cards: CardData[];
  onCardClick: (card: CardData) => void;
  initData: string | null;
}

const COLUMNS = 3;
const GAP = 10;
const PADDING = 10;

const AllCards: React.FC<AllCardsProps> = memo(({ cards, onCardClick, initData }) => {
  const parentRef = useRef<HTMLDivElement>(null);
  const { getImage, isLoading, hasFailed, setVisibleRange } = useVirtualizedImages(cards, initData);

  const rowCount = Math.ceil(cards.length / COLUMNS);

  const virtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 200,
    overscan: 5,
    paddingStart: PADDING,
    paddingEnd: PADDING,
  });

  const virtualRows = virtualizer.getVirtualItems();

  // Notify image loader of visible range
  useEffect(() => {
    if (virtualRows.length === 0) return;
    setVisibleRange(virtualRows[0].index, virtualRows[virtualRows.length - 1].index, COLUMNS);
  }, [virtualRows, setVisibleRange]);

  const handleCardClick = useCallback((card: CardData) => onCardClick(card), [onCardClick]);

  return (
    <div ref={parentRef} className="all-cards-container virtualized-container">
      <div className="virtualized-content" style={{ height: virtualizer.getTotalSize() }}>
        {virtualRows.map((row) => (
          <div
            key={row.key}
            data-index={row.index}
            ref={virtualizer.measureElement}
            className="virtualized-row"
            style={{ transform: `translateY(${row.start}px)`, padding: `0 ${PADDING}px ${GAP}px` }}
          >
            <div className="virtualized-row-grid" style={{ gridTemplateColumns: `repeat(${COLUMNS}, 1fr)`, gap: GAP }}>
              {cards.slice(row.index * COLUMNS, (row.index + 1) * COLUMNS).map((card) => (
                <MiniCard
                  key={card.id}
                  card={card}
                  imageB64={getImage(card.id)}
                  isLoading={isLoading(card.id)}
                  hasFailed={hasFailed(card.id)}
                  onClick={handleCardClick}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
});

AllCards.displayName = 'AllCards';
export default AllCards;
