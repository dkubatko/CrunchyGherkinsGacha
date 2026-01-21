// src/lib/imageCache.ts

import { persistentImageCache, type ImageVariant } from './persistentImageCache';

interface CacheEntry {
  data: string;
  timestamp: number;
  imageUpdatedAt: string | null;
}

/**
 * Hybrid image cache with in-memory fast path and IndexedDB persistence.
 * 
 * - In-memory for instant access during session
 * - IndexedDB for persistence across sessions
 * - Timestamp validation via image_updated_at
 */
class ImageCache {
  private cache: Map<string, CacheEntry> = new Map();
  private readonly CACHE_DURATION = 30 * 60 * 1000; // 30 minutes for in-memory TTL
  
  // Track pending persistent loads to avoid duplicate fetches
  private pendingLoads = new Map<string, Promise<string | null>>();

  private getKey(cardId: number, variant: ImageVariant): string {
    return `${variant}:${cardId}`;
  }

  /**
   * Store image in both in-memory and persistent cache.
   */
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

  /**
   * Get image from in-memory cache only (synchronous, fast path).
   * Use getAsync for persistent cache fallback.
   */
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

  /**
   * Get image from cache, checking persistent storage if not in memory.
   * Also validates against server timestamp if provided.
   */
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

    // Slow path: check persistent cache
    const loadPromise = (async () => {
      try {
        // Validate against server timestamp before loading from persistent
        if (serverImageUpdatedAt && !persistentImageCache.isValid(cardId, variant, serverImageUpdatedAt)) {
          // Persistent cache is stale
          return null;
        }

        const data = await persistentImageCache.get(cardId, variant);
        if (data) {
          // Promote to in-memory cache
          this.cache.set(key, {
            data,
            timestamp: Date.now(),
            imageUpdatedAt: serverImageUpdatedAt,  // Use server timestamp since we validated
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

  /**
   * Check if image is in in-memory cache (synchronous).
   */
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

  /**
   * Check if image exists in either memory or persistent cache.
   * Does NOT validate timestamp - use isValidCached for that.
   */
  hasAny(cardId: number, variant: ImageVariant = 'full'): boolean {
    if (this.has(cardId, variant)) {
      return true;
    }
    return persistentImageCache.has(cardId, variant);
  }

  /**
   * Check if a valid (non-stale) cached version exists.
   */
  isValidCached(cardId: number, variant: ImageVariant, serverImageUpdatedAt: string | null): boolean {
    const key = this.getKey(cardId, variant);
    
    // Check in-memory first
    const memEntry = this.cache.get(key);
    if (memEntry) {
      const isExpired = Date.now() - memEntry.timestamp > this.CACHE_DURATION;
      if (!isExpired) {
        if (!serverImageUpdatedAt) return true;
        if (!memEntry.imageUpdatedAt) return false;
        return new Date(memEntry.imageUpdatedAt) >= new Date(serverImageUpdatedAt);
      }
    }

    // Check persistent cache
    return persistentImageCache.isValid(cardId, variant, serverImageUpdatedAt);
  }

  clear(): void {
    this.cache.clear();
    // Note: intentionally not clearing persistent cache on clear()
    // Use clearAll() to also clear persistent storage
  }

  async clearAll(): Promise<void> {
    this.cache.clear();
    await persistentImageCache.clear();
  }

  size(): number {
    return this.cache.size;
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

  /**
   * Get cache statistics for debugging.
   */
  getStats(): { memorySize: number; persistentStats: ReturnType<typeof persistentImageCache.getStats> } {
    return {
      memorySize: this.cache.size,
      persistentStats: persistentImageCache.getStats(),
    };
  }

  /**
   * Preload images from persistent cache into memory.
   * Useful for hydrating cache on app start.
   */
  async preloadFromPersistent(cardIds: number[], variant: ImageVariant = 'thumb'): Promise<void> {
    const loadPromises = cardIds.map(async (cardId) => {
      if (!this.has(cardId, variant)) {
        await this.getAsync(cardId, variant);
      }
    });
    await Promise.all(loadPromises);
  }
}

export const imageCache = new ImageCache();

// Re-export types for convenience
export type { ImageVariant };

// Clean up expired entries every 5 minutes
setInterval(() => {
  imageCache.cleanup();
}, 5 * 60 * 1000);

