// src/lib/imageCache.ts

type ImageVariant = 'full' | 'thumb';

interface CacheEntry {
  data: string;
  timestamp: number;
}

class ImageCache {
  private cache: Map<string, CacheEntry> = new Map();
  private readonly CACHE_DURATION = 30 * 60 * 1000; // 30 minutes

  private getKey(cardId: number, variant: ImageVariant): string {
    return `${variant}:${cardId}`;
  }

  set(cardId: number, data: string, variant: ImageVariant = 'full'): void {
    const key = this.getKey(cardId, variant);
    this.cache.set(key, {
      data,
      timestamp: Date.now()
    });
  }

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

  clear(): void {
    this.cache.clear();
  }

  size(): number {
    return this.cache.size;
  }

  // Clean up expired entries
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

// Clean up expired entries every 5 minutes
setInterval(() => {
  imageCache.cleanup();
}, 5 * 60 * 1000);
