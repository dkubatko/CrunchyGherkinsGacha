/**
 * Simple in-memory image cache with TTL expiration.
 */

export type ImageVariant = 'full' | 'thumb';

interface CacheEntry {
  data: string;
  timestamp: number;
  imageUpdatedAt: string | null;
}

const TTL_MS = 30 * 60 * 1000; // 30 minutes

class MemoryImageCache {
  private cache = new Map<string, CacheEntry>();

  private getKey(cardId: number, variant: ImageVariant): string {
    return `${variant}:${cardId}`;
  }

  set(cardId: number, variant: ImageVariant, data: string, imageUpdatedAt: string | null = null): void {
    this.cache.set(this.getKey(cardId, variant), {
      data,
      timestamp: Date.now(),
      imageUpdatedAt,
    });
  }

  get(cardId: number, variant: ImageVariant): string | null {
    const entry = this.cache.get(this.getKey(cardId, variant));
    if (!entry) return null;

    if (Date.now() - entry.timestamp > TTL_MS) {
      this.cache.delete(this.getKey(cardId, variant));
      return null;
    }
    return entry.data;
  }

  has(cardId: number, variant: ImageVariant): boolean {
    return this.get(cardId, variant) !== null;
  }

  delete(cardId: number, variant: ImageVariant): void {
    this.cache.delete(this.getKey(cardId, variant));
  }

  cleanup(): void {
    const now = Date.now();
    for (const [key, entry] of this.cache) {
      if (now - entry.timestamp > TTL_MS) {
        this.cache.delete(key);
      }
    }
  }
}

export const memoryImageCache = new MemoryImageCache();

// Cleanup expired entries periodically
setInterval(() => memoryImageCache.cleanup(), 5 * 60 * 1000);
