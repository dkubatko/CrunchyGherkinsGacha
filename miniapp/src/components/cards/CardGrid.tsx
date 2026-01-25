import React, { memo, useCallback, useRef, useLayoutEffect, useMemo, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import MiniCard from './MiniCard';
import { useVirtualizedImages } from '@/hooks';
import './CardGrid.css';
import type { CardData } from '@/types';

interface CardGridProps {
  cards: CardData[];
  onCardClick: (card: CardData) => void;
  initData: string | null;
}

const COLUMNS = 3;
const GAP = 10;
const PADDING = 10;

const getRowHeightFromWidth = (width: number) => {
  const safeWidth = Math.max(1, width);
  const totalHorizontalPadding = PADDING * 2;
  const totalGap = GAP * (COLUMNS - 1);
  const cardWidth = Math.max(0, (safeWidth - totalHorizontalPadding - totalGap) / COLUMNS);
  const cardHeight = cardWidth * 1.8; // Matches .grid-card padding-top: 180%
  return Math.ceil(cardHeight + GAP);
};

const CardGrid: React.FC<CardGridProps> = memo(({ cards, onCardClick, initData }) => {
  const parentRef = useRef<HTMLDivElement>(null);
  const { getImage, isLoading, hasFailed, setVisibleRange } = useVirtualizedImages(cards, initData);
  const [containerWidth, setContainerWidth] = useState(0);
  const lastWidthRef = useRef(0);

  const rowCount = Math.ceil(cards.length / COLUMNS);

  // Compute a stable row height from the actual container width.
  // This keeps virtualization in sync with the CSS aspect ratio and avoids scroll jank.
  const rowHeight = useMemo(() => {
    const fallbackWidth = lastWidthRef.current || parentRef.current?.clientWidth || window.innerWidth;
    return getRowHeightFromWidth(containerWidth || fallbackWidth);
  }, [containerWidth]);

  const virtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 5,
    paddingStart: PADDING,
    paddingEnd: PADDING,
  });

  const virtualRows = virtualizer.getVirtualItems();

  // Measure container width synchronously on mount and on resize.
  // A correct initial width prevents one-frame mis-estimation on tab switches.
  useLayoutEffect(() => {
    const el = parentRef.current;
    if (!el) return;

    const initialWidth = el.clientWidth;
    if (initialWidth && initialWidth !== lastWidthRef.current) {
      lastWidthRef.current = initialWidth;
      setContainerWidth(initialWidth);
    }

    const observer = new ResizeObserver((entries) => {
      if (!entries[0]) return;
      const nextWidth = entries[0].contentRect.width;
      if (nextWidth && nextWidth !== lastWidthRef.current) {
        lastWidthRef.current = nextWidth;
        setContainerWidth(nextWidth);
      }
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Re-measure when row height changes to keep the virtualizer aligned.
  useLayoutEffect(() => {
    virtualizer.measure();
  }, [rowHeight, virtualizer]);

  // Notify image loader of visible range
  // Include cards in deps so images reload when filter/sort changes the card list
  useLayoutEffect(() => {
    if (virtualRows.length === 0) return;
    setVisibleRange(virtualRows[0].index, virtualRows[virtualRows.length - 1].index, COLUMNS);
  }, [virtualRows, setVisibleRange, cards]);

  const handleCardClick = useCallback((card: CardData) => onCardClick(card), [onCardClick]);

  return (
    <div ref={parentRef} className="all-cards-container virtualized-container">
      <div className="virtualized-content" style={{ height: virtualizer.getTotalSize() }}>
        {virtualRows.map((row) => (
          <div
            key={row.key}
            data-index={row.index}
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

CardGrid.displayName = 'CardGrid';
export default CardGrid;
