// src/lib/imageCache.ts
// Hybrid cache: in-memory (fast) + IndexedDB (persistent)
// Use getAsync() for full cache check, get() for memory-only

import { persistentImageCache, type ImageVariant } from './persistentImageCache';

interface CacheEntry {
  data: string;
  timestamp: number;
  imageUpdatedAt: string | null;
}

class ImageCache {
  private cache: Map<string, CacheEntry> = new Map();
  private readonly CACHE_DURATION = 30 * 60 * 1000; // 30 minutes for in-memory TTL
  
  // Track pending persistent loads to avoid duplicate fetches
  private pendingLoads = new Map<string, Promise<string | null>>();

  private getKey(cardId: number, variant: ImageVariant): string {
    return `${variant}:${cardId}`;
  }

  /** Store in memory + async persist to IndexedDB */
  set(cardId: number, data: string, variant: ImageVariant = 'full', imageUpdatedAt: string | null = null): void {
    const key = this.getKey(cardId, variant);
    this.cache.set(key, {
      data,
      timestamp: Date.now(),
      imageUpdatedAt,
    });
    
    // Async persist to IndexedDB (fire and forget)
    persistentImageCache.set(cardId, variant, data, imageUpdatedAt).catch(() => {
      // Silent fail - in-memory cache still works
    });
  }

  /** Get from memory only (sync). Use getAsync() for full check. */
  get(cardId: number, variant: ImageVariant = 'full'): string | null {
    const key = this.getKey(cardId, variant);
    const entry = this.cache.get(key);
    if (!entry) {
      return null;
    }

    const isExpired = Date.now() - entry.timestamp > this.CACHE_DURATION;
    if (isExpired) {
      this.cache.delete(key);
      return null;
    }

    return entry.data;
  }

  /** Primary cache check: memory → IndexedDB. Validates timestamp, promotes to memory. */
  async getAsync(
    cardId: number, 
    variant: ImageVariant = 'full',
    serverImageUpdatedAt: string | null = null
  ): Promise<string | null> {
    const key = this.getKey(cardId, variant);
    
    // Fast path: check in-memory cache first
    const memEntry = this.cache.get(key);
    if (memEntry) {
      const isExpired = Date.now() - memEntry.timestamp > this.CACHE_DURATION;
      if (!isExpired) {
        // Validate against server timestamp if provided
        if (serverImageUpdatedAt && memEntry.imageUpdatedAt) {
          if (new Date(memEntry.imageUpdatedAt) < new Date(serverImageUpdatedAt)) {
            // Cache is stale, remove and return null
            this.cache.delete(key);
            return null;
          }
        }
        return memEntry.data;
      }
      this.cache.delete(key);
    }

    // Check if we're already loading this from persistent storage
    const pending = this.pendingLoads.get(key);
    if (pending) {
      return pending;
    }

    // Slow path: check persistent cache (awaits DB ready)
    const loadPromise = (async () => {
      try {
        // Validate against server timestamp before loading from persistent
        if (serverImageUpdatedAt) {
          const isValid = await persistentImageCache.isValidAsync(cardId, variant, serverImageUpdatedAt);
          if (!isValid) {
            return null;
          }
        }

        const data = await persistentImageCache.get(cardId, variant);
        if (data) {
          // Promote to in-memory cache
          this.cache.set(key, {
            data,
            timestamp: Date.now(),
            imageUpdatedAt: serverImageUpdatedAt,
          });
        }
        return data;
      } finally {
        this.pendingLoads.delete(key);
      }
    })();

    this.pendingLoads.set(key, loadPromise);
    return loadPromise;
  }

  /** Check memory cache only (sync) */
  has(cardId: number, variant: ImageVariant = 'full'): boolean {
    const key = this.getKey(cardId, variant);
    const entry = this.cache.get(key);
    if (!entry) {
      return false;
    }

    const isExpired = Date.now() - entry.timestamp > this.CACHE_DURATION;
    if (isExpired) {
      this.cache.delete(key);
      return false;
    }

    return true;
  }

  // Clean up expired entries from in-memory cache
  cleanup(): void {
    const now = Date.now();
    for (const [key, entry] of this.cache.entries()) {
      const isExpired = now - entry.timestamp > this.CACHE_DURATION;
      if (isExpired) {
        this.cache.delete(key);
      }
    }
  }
}

export const imageCache = new ImageCache();

// Re-export types for convenience
export type { ImageVariant };

// Clean up expired entries every 5 minutes
setInterval(() => {
  imageCache.cleanup();
}, 5 * 60 * 1000);

