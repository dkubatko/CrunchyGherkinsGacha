// src/lib/imageCache.ts

interface CacheEntry {
  data: string;
  timestamp: number;
}

class ImageCache {
  private cache: Map<number, CacheEntry> = new Map();
  private readonly CACHE_DURATION = 30 * 60 * 1000; // 30 minutes

  set(cardId: number, data: string): void {
    this.cache.set(cardId, {
      data,
      timestamp: Date.now()
    });
  }

  get(cardId: number): string | null {
    const entry = this.cache.get(cardId);
    if (!entry) {
      return null;
    }

    const isExpired = Date.now() - entry.timestamp > this.CACHE_DURATION;
    if (isExpired) {
      this.cache.delete(cardId);
      return null;
    }

    return entry.data;
  }

  has(cardId: number): boolean {
    const entry = this.cache.get(cardId);
    if (!entry) {
      return false;
    }

    const isExpired = Date.now() - entry.timestamp > this.CACHE_DURATION;
    if (isExpired) {
      this.cache.delete(cardId);
      return false;
    }

    return true;
  }

  clear(): void {
    this.cache.clear();
  }

  size(): number {
    return this.cache.size;
  }

  // Clean up expired entries
  cleanup(): void {
    const now = Date.now();
    for (const [cardId, entry] of this.cache.entries()) {
      const isExpired = now - entry.timestamp > this.CACHE_DURATION;
      if (isExpired) {
        this.cache.delete(cardId);
      }
    }
  }
}

export const imageCache = new ImageCache();

// Clean up expired entries every 5 minutes
setInterval(() => {
  imageCache.cleanup();
}, 5 * 60 * 1000);
