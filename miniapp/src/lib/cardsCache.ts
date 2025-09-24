// src/lib/cardsCache.ts
import type { CardData } from '../types';

interface CacheEntry {
  data: CardData[];
  timestamp: number;
  cacheKey: string;
}

class CardsCache {
  private cache: CacheEntry | null = null;
  private readonly CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

  // Create a simple cache key from init data
  private createCacheKey(initData: string): string {
    // Use a simple hash of the initData for cache key
    let hash = 0;
    for (let i = 0; i < initData.length; i++) {
      const char = initData.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    return hash.toString();
  }

  set(data: CardData[], initData: string): void {
    this.cache = {
      data,
      timestamp: Date.now(),
      cacheKey: this.createCacheKey(initData)
    };
  }

  get(initData: string): CardData[] | null {
    if (!this.cache || this.cache.cacheKey !== this.createCacheKey(initData)) {
      return null;
    }

    const isExpired = Date.now() - this.cache.timestamp > this.CACHE_DURATION;
    if (isExpired) {
      this.cache = null;
      return null;
    }

    return this.cache.data;
  }

  clear(): void {
    this.cache = null;
  }

  isValid(initData: string): boolean {
    if (!this.cache || this.cache.cacheKey !== this.createCacheKey(initData)) {
      return false;
    }

    const isExpired = Date.now() - this.cache.timestamp > this.CACHE_DURATION;
    return !isExpired;
  }
}

export const cardsCache = new CardsCache();