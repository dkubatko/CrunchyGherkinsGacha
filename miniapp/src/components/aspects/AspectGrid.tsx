import React, { memo, useCallback, useRef, useLayoutEffect, useMemo, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import MiniAspect from './MiniAspect';
import { useVirtualizedAspectImages } from '@/hooks/useVirtualizedAspectImages';
import '@/components/cards/CardGrid.css';
import type { AspectData } from '@/types';

interface AspectGridProps {
  aspects: AspectData[];
  onAspectClick: (aspect: AspectData) => void;
  initData: string | null;
}

const COLUMNS = 3;
const GAP = 10;
const PADDING = 10;
const INFO_HEIGHT = 36;

const getRowHeightFromWidth = (width: number) => {
  const safeWidth = Math.max(1, width);
  const totalHorizontalPadding = PADDING * 2;
  const totalGap = GAP * (COLUMNS - 1);
  const cardWidth = Math.max(0, (safeWidth - totalHorizontalPadding - totalGap) / COLUMNS);
  const cardHeight = cardWidth + INFO_HEIGHT; // 1:1 image + info bar
  return Math.ceil(cardHeight + GAP);
};

const AspectGrid: React.FC<AspectGridProps> = memo(({ aspects, onAspectClick, initData }) => {
  const parentRef = useRef<HTMLDivElement>(null);
  const { getImage, isLoading, hasFailed, setVisibleRange } = useVirtualizedAspectImages(aspects, initData);
  const [containerWidth, setContainerWidth] = useState(0);
  const lastWidthRef = useRef(0);

  const rows = useMemo(() => {
    const result: AspectData[][] = [];
    for (let i = 0; i < aspects.length; i += COLUMNS) {
      result.push(aspects.slice(i, i + COLUMNS));
    }
    return result;
  }, [aspects]);

  const rowCount = rows.length;

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
    onChange: (instance) => {
      const items = instance.getVirtualItems();
      if (items.length === 0) return;
      setVisibleRange(items[0].index, items[items.length - 1].index, COLUMNS);
    },
  });

  const virtualRows = virtualizer.getVirtualItems();

  useLayoutEffect(() => {
    const items = virtualizer.getVirtualItems();
    if (items.length === 0) return;
    setVisibleRange(items[0].index, items[items.length - 1].index, COLUMNS);
  }, [aspects, virtualizer, setVisibleRange]);

  useLayoutEffect(() => {
    const el = parentRef.current;
    if (!el) return;

    const initialWidth = el.clientWidth;
    if (initialWidth && initialWidth !== lastWidthRef.current) {
      lastWidthRef.current = initialWidth;
      setContainerWidth(initialWidth);
    }
    if (initialWidth > 0) {
      requestAnimationFrame(() => {
        virtualizer.measure();
      });
    }

    const observer = new ResizeObserver((entries) => {
      if (!entries[0]) return;
      const nextWidth = entries[0].contentRect.width;
      if (!nextWidth) return;

      if (nextWidth !== lastWidthRef.current) {
        lastWidthRef.current = nextWidth;
        setContainerWidth(nextWidth);
      }

      requestAnimationFrame(() => {
        virtualizer.measure();
      });
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, [virtualizer]);

  useLayoutEffect(() => {
    virtualizer.measure();
  }, [rowHeight, virtualizer]);

  const handleAspectClick = useCallback((aspect: AspectData) => onAspectClick(aspect), [onAspectClick]);

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
              {(rows[row.index] ?? []).map((aspect) => (
                <MiniAspect
                  key={aspect.id}
                  aspect={aspect}
                  imageB64={getImage(aspect.id)}
                  isLoading={isLoading(aspect.id)}
                  hasFailed={hasFailed(aspect.id)}
                  onClick={handleAspectClick}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
});

AspectGrid.displayName = 'AspectGrid';
export default AspectGrid;
