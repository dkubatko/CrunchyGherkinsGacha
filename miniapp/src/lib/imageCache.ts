/**
 * Minimal image cache facade for Card/Aspect/SingleView components.
 * For thumbnail loading in grids, use useVirtualized*Images hooks directly.
 */

import { memoryImageCache, type ImageVariant } from './memoryImageCache';
import { persistentImageCache } from './persistentImageCache';

/** Offset aspect IDs to avoid collisions with card IDs in the shared cache. */
export const aspectCacheId = (id: number) => id + 1_000_000_000;

export const imageCache = {
  /** Store in both memory and IndexedDB */
  set(cardId: number, data: string, variant: ImageVariant = 'full', imageUpdatedAt: string | null = null): void {
    memoryImageCache.set(cardId, variant, data, imageUpdatedAt);
    persistentImageCache.set(cardId, variant, data, imageUpdatedAt).catch(() => {});
  },

  /** Sync check memory cache only */
  has(cardId: number, variant: ImageVariant = 'full'): boolean {
    return memoryImageCache.has(cardId, variant);
  },

  /** Async get: memory → IndexedDB */
  async getAsync(cardId: number, variant: ImageVariant = 'full', serverTimestamp: string | null = null): Promise<string | null> {
    const memData = memoryImageCache.get(cardId, variant);
    if (memData) return memData;

    const data = await persistentImageCache.get(cardId, variant, serverTimestamp);
    if (data) {
      memoryImageCache.set(cardId, variant, data, serverTimestamp);
    }
    return data;
  },
};
