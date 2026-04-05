import { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { memoryImageCache } from '../lib/memoryImageCache';
import { persistentImageCache } from '../lib/persistentImageCache';
import { aspectCacheId } from '../lib/imageCache';
import { fetchAspectImages } from '../services/aspectImageApiService';
import type { AspectData } from '../types';

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

export interface UseVirtualizedAspectImagesReturn {
  getImage: (aspectId: number) => string | null;
  isLoading: (aspectId: number) => boolean;
  hasFailed: (aspectId: number) => boolean;
  setVisibleRange: (startRow: number, endRow: number, columns: number) => void;
}

export function useVirtualizedAspectImages(
  aspects: AspectData[],
  initData: string | null
): UseVirtualizedAspectImagesReturn {
  const [images, setImages] = useState<Map<number, string>>(new Map());

  const imagesRef = useRef<Map<number, string>>(new Map());
  const loadingRef = useRef<Set<number>>(new Set());
  const failedRef = useRef<Set<number>>(new Set());

  const aspectIds = useMemo(() => aspects.map(a => a.id), [aspects]);

  // Reset when aspects change
  useEffect(() => {
    setImages(new Map());
    imagesRef.current = new Map();
    loadingRef.current.clear();
    failedRef.current.clear();
  }, [aspects]);

  const initDataRef = useRef(initData);
  initDataRef.current = initData;

  const fetchBatch = useCallback(async (ids: number[]) => {
    if (!initDataRef.current || ids.length === 0) return;

    try {
      const result = await fetchAspectImages(ids, initDataRef.current);
      const newImages: Array<[number, string]> = [];

      for (const [aspectId, data] of result.loaded.entries()) {
        await decodeImage(data);
        const cacheKey = aspectCacheId(aspectId);
        memoryImageCache.set(cacheKey, 'thumb', data, null);
        persistentImageCache.set(cacheKey, 'thumb', data, null).catch(() => {});
        imagesRef.current.set(aspectId, data);
        newImages.push([aspectId, data]);
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
  }, []);

  const aspectIdsRef = useRef(aspectIds);
  aspectIdsRef.current = aspectIds;

  const setVisibleRange = useCallback((startRow: number, endRow: number, columns: number) => {
    const ids = aspectIdsRef.current;
    const startIdx = Math.max(0, (startRow - OVERSCAN_ROWS) * columns);
    const endIdx = Math.min(ids.length, (endRow + OVERSCAN_ROWS + 1) * columns);
    const visibleIds = ids.slice(startIdx, endIdx);

    const fromMemory: Array<[number, string]> = [];
    const toCheckDb: number[] = [];

    for (const id of visibleIds) {
      if (imagesRef.current.has(id) || loadingRef.current.has(id) || failedRef.current.has(id)) {
        continue;
      }

      const cacheKey = aspectCacheId(id);
      const cached = memoryImageCache.get(cacheKey, 'thumb');
      if (cached) {
        imagesRef.current.set(id, cached);
        fromMemory.push([id, cached]);
        decodeImage(cached).catch(() => {});
        continue;
      }

      toCheckDb.push(id);
    }

    toCheckDb.forEach(id => loadingRef.current.add(id));

    if (fromMemory.length > 0) {
      setImages(prev => {
        const next = new Map(prev);
        fromMemory.forEach(([id, data]) => next.set(id, data));
        return next;
      });
    }

    if (toCheckDb.length > 0) {
      Promise.all(
        toCheckDb.map(async (id) => {
          const cacheKey = aspectCacheId(id);
          const data = await persistentImageCache.get(cacheKey, 'thumb', null);

          if (data) {
            memoryImageCache.set(cacheKey, 'thumb', data, null);
            imagesRef.current.set(id, data);
            loadingRef.current.delete(id);
            return [id, data] as [number, string];
          } else {
            return id;
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

        for (let i = 0; i < toFetch.length; i += BATCH_SIZE) {
          fetchBatch(toFetch.slice(i, i + BATCH_SIZE));
        }
      });
    }
  }, [fetchBatch]);

  return {
    getImage: useCallback((id: number) => {
      const cacheKey = aspectCacheId(id);
      const cached = memoryImageCache.get(cacheKey, 'thumb');
      if (cached) return cached;
      return images.get(id) ?? null;
    }, [images]),
    isLoading: useCallback((id: number) => loadingRef.current.has(id), []),
    hasFailed: useCallback((id: number) => failedRef.current.has(id), []),
    setVisibleRange,
  };
}
