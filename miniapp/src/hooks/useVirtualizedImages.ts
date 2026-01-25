import { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { memoryImageCache } from '../lib/memoryImageCache';
import { persistentImageCache } from '../lib/persistentImageCache';
import { fetchCardImages } from '../services/imageApiService';
import type { CardData } from '../types';

const BATCH_SIZE = 3;      // Backend limit per request
const OVERSCAN_ROWS = 5;   // Extra rows to preload

type DecodableImage = HTMLImageElement & { decode?: () => Promise<void> };

const decodeImage = async (base64: string) => {
  try {
    const img = new Image() as DecodableImage;
    img.src = `data:image/png;base64,${base64}`;

    if (img.decode) {
      await img.decode();
      return;
    }

    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error('Image decode failed'));
    });
  } catch {
    // Ignore decode failures; rendering will still attempt to display the image.
  }
};

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

  // Store refs for stable callback identity
  const initDataRef = useRef(initData);
  const cardMapRef = useRef(cardMap);
  initDataRef.current = initData;
  cardMapRef.current = cardMap;

  // Fetch a batch of card images from server - stable identity via refs
  const fetchBatch = useCallback(async (ids: number[]) => {
    if (!initDataRef.current || ids.length === 0) return;

    try {
      const result = await fetchCardImages(ids, initDataRef.current);
      const newImages: Array<[number, string]> = [];

      for (const [cardId, data] of result.loaded.entries()) {
        const timestamp = cardMapRef.current.get(cardId)?.image_updated_at ?? null;
        await decodeImage(data);
        memoryImageCache.set(cardId, 'thumb', data, timestamp);
        persistentImageCache.set(cardId, 'thumb', data, timestamp).catch(() => {});
        imagesRef.current.set(cardId, data);
        newImages.push([cardId, data]);
      }

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
  }, []); // Empty deps - uses refs for values

  // Store cardIds in ref for stable setVisibleRange
  const cardIdsRef = useRef(cardIds);
  cardIdsRef.current = cardIds;

  // Load images for visible range - stable identity via refs
  const setVisibleRange = useCallback((startRow: number, endRow: number, columns: number) => {
    const ids = cardIdsRef.current;
    const startIdx = Math.max(0, (startRow - OVERSCAN_ROWS) * columns);
    const endIdx = Math.min(ids.length, (endRow + OVERSCAN_ROWS + 1) * columns);
    const visibleIds = ids.slice(startIdx, endIdx);

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
        decodeImage(cached).catch(() => {});
        continue;
      }

      toCheckDb.push(id);
    }

    // Mark as loading BEFORE async work to prevent race conditions
    toCheckDb.forEach(id => loadingRef.current.add(id));

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
          const timestamp = cardMapRef.current.get(id)?.image_updated_at ?? null;
          const data = await persistentImageCache.get(id, 'thumb', timestamp);

          if (data) {
            memoryImageCache.set(id, 'thumb', data, timestamp);
            imagesRef.current.set(id, data);
            loadingRef.current.delete(id); // Found in DB, no longer loading
            return [id, data] as [number, string];
          } else {
            return id; // Return ID to fetch from server (already in loadingRef)
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
          Promise.all(dbResults.map(async ([id, data]) => {
            await decodeImage(data);
            return [id, data] as [number, string];
          })).then((decoded) => {
            setImages(prev => {
              const next = new Map(prev);
              decoded.forEach(([id, data]) => next.set(id, data));
              return next;
            });
          });
        }

        // Fire server fetches in parallel
        for (let i = 0; i < toFetch.length; i += BATCH_SIZE) {
          fetchBatch(toFetch.slice(i, i + BATCH_SIZE));
        }
      });
    }
  }, [fetchBatch]); // Only depends on stable fetchBatch

  return {
    getImage: useCallback((id: number) => {
      // Check memory cache first for immediate display (avoids waiting for state update)
      const cached = memoryImageCache.get(id, 'thumb');
      if (cached) return cached;
      return images.get(id) ?? null;
    }, [images]),
    isLoading: useCallback((id: number) => loadingRef.current.has(id), []),
    hasFailed: useCallback((id: number) => failedRef.current.has(id), []),
    setVisibleRange,
  };
}

