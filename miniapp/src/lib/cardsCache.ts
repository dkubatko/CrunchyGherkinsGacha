// src/lib/cardsCache.ts
import type { CardData } from '../types';

interface CacheEntry {
  data: CardData[];
  timestamp: number;
  authToken: string;
}

class CardsCache {
  private cache: CacheEntry | null = null;
  private readonly CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

  set(data: CardData[], authToken: string): void {
    this.cache = {
      data,
      timestamp: Date.now(),
      authToken
    };
  }

  get(authToken: string): CardData[] | null {
    if (!this.cache || this.cache.authToken !== authToken) {
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

  isValid(authToken: string): boolean {
    if (!this.cache || this.cache.authToken !== authToken) {
      return false;
    }

    const isExpired = Date.now() - this.cache.timestamp > this.CACHE_DURATION;
    return !isExpired;
  }
}

export const cardsCache = new CardsCache();