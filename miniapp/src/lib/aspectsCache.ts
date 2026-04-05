// src/lib/aspectsCache.ts
import type { AspectData } from '../types';

interface CacheEntry {
  data: AspectData[];
  timestamp: number;
}

class AspectsCache {
  private cache = new Map<string, CacheEntry>();
  private readonly CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

  private createCacheKey(initData: string, chatId: string | null): string {
    const compositeKey = `${initData}::${chatId ?? 'all'}`;
    let hash = 0;
    for (let i = 0; i < compositeKey.length; i++) {
      const char = compositeKey.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return hash.toString();
  }

  set(data: AspectData[], initData: string, chatId: string | null = null): void {
    const cacheKey = this.createCacheKey(initData, chatId);
    this.cache.set(cacheKey, {
      data,
      timestamp: Date.now()
    });
  }

  get(initData: string, chatId: string | null = null): AspectData[] | null {
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
}

export const aspectsCache = new AspectsCache();
