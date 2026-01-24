import { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { memoryImageCache } from '../lib/memoryImageCache';
import { persistentImageCache } from '../lib/persistentImageCache';
import { fetchCardImages } from '../services/imageApiService';
import type { CardData } from '../types';

const BATCH_SIZE = 3;      // Backend limit per request
const OVERSCAN_ROWS = 5;   // Extra rows to preload

export interface UseVirtualizedImagesReturn {
  getImage: (cardId: number) => string | null;
  isLoading: (cardId: number) => boolean;
  hasFailed: (cardId: number) => boolean;
  setVisibleRange: (startRow: number, endRow: number, columns: number) => void;
}

export function useVirtualizedImages(
  cards: CardData[],
  initData: string | null
): UseVirtualizedImagesReturn {
  const [images, setImages] = useState<Map<number, string>>(new Map());

  // Refs for tracking - avoid stale closures
  const imagesRef = useRef<Map<number, string>>(new Map());
  const loadingRef = useRef<Set<number>>(new Set());
  const failedRef = useRef<Set<number>>(new Set());

  // Memoize card data to avoid recreation
  const cardIds = useMemo(() => cards.map(c => c.id), [cards]);
  const cardMap = useMemo(() => new Map(cards.map(c => [c.id, c])), [cards]);

  // Reset when cards change
  useEffect(() => {
    setImages(new Map());
    imagesRef.current = new Map();
    loadingRef.current.clear();
    failedRef.current.clear();
  }, [cards]);

  // Fetch a batch of card images from server
  const fetchBatch = useCallback(async (ids: number[]) => {
    if (!initData || ids.length === 0) return;

    try {
      const result = await fetchCardImages(ids, initData);
      const newImages: Array<[number, string]> = [];

      result.loaded.forEach((data, cardId) => {
        const timestamp = cardMap.get(cardId)?.image_updated_at ?? null;
        memoryImageCache.set(cardId, 'thumb', data, timestamp);
        persistentImageCache.set(cardId, 'thumb', data, timestamp).catch(() => {});
        imagesRef.current.set(cardId, data);
        newImages.push([cardId, data]);
      });

      result.failed.forEach(id => failedRef.current.add(id));

      if (newImages.length > 0) {
        setImages(prev => {
          const next = new Map(prev);
          newImages.forEach(([id, data]) => next.set(id, data));
          return next;
        });
      }
    } finally {
      ids.forEach(id => loadingRef.current.delete(id));
    }
  }, [initData, cardMap]);

  // Load images for visible range
  const setVisibleRange = useCallback((startRow: number, endRow: number, columns: number) => {
    const startIdx = Math.max(0, (startRow - OVERSCAN_ROWS) * columns);
    const endIdx = Math.min(cardIds.length, (endRow + OVERSCAN_ROWS + 1) * columns);
    const visibleIds = cardIds.slice(startIdx, endIdx);

    const fromMemory: Array<[number, string]> = [];
    const toCheckDb: number[] = [];

    for (const id of visibleIds) {
      if (imagesRef.current.has(id) || loadingRef.current.has(id) || failedRef.current.has(id)) {
        continue;
      }

      const cached = memoryImageCache.get(id, 'thumb');
      if (cached) {
        imagesRef.current.set(id, cached);
        fromMemory.push([id, cached]);
        continue;
      }

      toCheckDb.push(id);
    }

    if (fromMemory.length > 0) {
      setImages(prev => {
        const next = new Map(prev);
        fromMemory.forEach(([id, data]) => next.set(id, data));
        return next;
      });
    }

    if (toCheckDb.length > 0) {
      // Parallel IndexedDB lookups
      Promise.all(
        toCheckDb.map(async (id) => {
          if (imagesRef.current.has(id) || loadingRef.current.has(id)) return null;

          const timestamp = cardMap.get(id)?.image_updated_at ?? null;
          const data = await persistentImageCache.get(id, 'thumb', timestamp);

          if (data) {
            memoryImageCache.set(id, 'thumb', data, timestamp);
            imagesRef.current.set(id, data);
            return [id, data] as [number, string];
          } else {
            loadingRef.current.add(id);
            return id; // Return ID to fetch
          }
        })
      ).then((results) => {
        const dbResults: Array<[number, string]> = [];
        const toFetch: number[] = [];

        for (const r of results) {
          if (r === null) continue;
          if (Array.isArray(r)) dbResults.push(r);
          else toFetch.push(r);
        }

        if (dbResults.length > 0) {
          setImages(prev => {
            const next = new Map(prev);
            dbResults.forEach(([id, data]) => next.set(id, data));
            return next;
          });
        }

        // Fire server fetches in parallel
        for (let i = 0; i < toFetch.length; i += BATCH_SIZE) {
          fetchBatch(toFetch.slice(i, i + BATCH_SIZE));
        }
      });
    }
  }, [cardIds, cardMap, fetchBatch]);

  return {
    getImage: useCallback((id: number) => images.get(id) ?? null, [images]),
    isLoading: useCallback((id: number) => loadingRef.current.has(id), []),
    hasFailed: useCallback((id: number) => failedRef.current.has(id), []),
    setVisibleRange,
  };
}

