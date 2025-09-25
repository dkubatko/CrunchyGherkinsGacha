// src/lib/cardsCache.ts
import type { CardData } from '../types';

interface CacheEntry {
  data: CardData[];
  timestamp: number;
}

class CardsCache {
  private cache = new Map<string, CacheEntry>();
  private readonly CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

  // Create a simple cache key from init data
  private createCacheKey(initData: string, chatId: string | null): string {
    const compositeKey = `${initData}::${chatId ?? 'all'}`;
    // Use a simple hash of the composite key for cache key
    let hash = 0;
    for (let i = 0; i < compositeKey.length; i++) {
      const char = compositeKey.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    return hash.toString();
  }

  set(data: CardData[], initData: string, chatId: string | null = null): void {
    const cacheKey = this.createCacheKey(initData, chatId);
    this.cache.set(cacheKey, {
      data,
      timestamp: Date.now()
    });
  }

  get(initData: string, chatId: string | null = null): CardData[] | null {
    const cacheKey = this.createCacheKey(initData, chatId);
    const entry = this.cache.get(cacheKey);

    if (!entry) {
      return null;
    }

    const isExpired = Date.now() - entry.timestamp > this.CACHE_DURATION;
    if (isExpired) {
      this.cache.delete(cacheKey);
      return null;
    }

    return entry.data;
  }

  clear(): void {
    this.cache.clear();
  }

  isValid(initData: string, chatId: string | null = null): boolean {
    const cacheKey = this.createCacheKey(initData, chatId);
    const entry = this.cache.get(cacheKey);

    if (!entry) {
      return false;
    }

    const isExpired = Date.now() - entry.timestamp > this.CACHE_DURATION;
    return !isExpired;
  }
}

export const cardsCache = new CardsCache();