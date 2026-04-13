import { useState, useEffect, useCallback, useRef } from 'react';
import type { AspectData } from '../types';
import { ApiService } from '../services/api';
import { aspectsCache } from '../lib/aspectsCache';

interface UseAllAspectsResult {
  allAspects: AspectData[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  updateAspect: (aspectId: number, updates: Partial<AspectData>) => void;
}

interface UseAllAspectsOptions {
  enabled?: boolean;
}

/**
 * Hook for fetching all aspects in a chat (read-only mode).
 */
export const useAllAspects = (
  initData: string | null,
  chatId: string | null = null,
  { enabled = true }: UseAllAspectsOptions = {},
): UseAllAspectsResult => {
  const cacheKey = chatId ?? null;
  const initialCachedAspects = initData && enabled ? aspectsCache.get(initData, cacheKey) : null;

  const [allAspects, setAllAspects] = useState<AspectData[]>(initialCachedAspects || []);
  const [loading, setLoading] = useState<boolean>(enabled && !initialCachedAspects);
  const [error, setError] = useState<string | null>(null);
  const prevEnabledRef = useRef(enabled);

  // Synchronously set loading when enabled flips to true (before render completes)
  if (enabled && !prevEnabledRef.current && !loading && allAspects.length === 0 && !error) {
    setLoading(true);
  }
  prevEnabledRef.current = enabled;

  const fetchAllAspects = useCallback(
    async (forceRefresh = false) => {
      if (!enabled) {
        setLoading(false);
        setError(null);
        setAllAspects([]);
        return;
      }

      if (!initData) {
        setError('No Telegram init data available');
        setLoading(false);
        return;
      }

      if (!forceRefresh) {
        const cachedAspects = aspectsCache.get(initData, cacheKey ?? null);
        if (cachedAspects) {
          setAllAspects(cachedAspects);
          setLoading(false);
          setError(null);
          return;
        }
        setAllAspects([]);
      }

      if (!forceRefresh) {
        setLoading(true);
      }
      setError(null);

      try {
        let aspects: AspectData[];
        if (chatId) {
          aspects = await ApiService.fetchAllChatAspects(initData, chatId);
        } else {
          aspects = [];
        }
        aspectsCache.set(aspects, initData, cacheKey ?? null);
        setAllAspects(aspects);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to fetch all aspects';
        setError(errorMessage);
      } finally {
        setLoading(false);
      }
    },
    [enabled, initData, chatId, cacheKey],
  );

  useEffect(() => {
    fetchAllAspects();
  }, [fetchAllAspects]);

  const refetch = useCallback(async () => {
    await fetchAllAspects(true);
  }, [fetchAllAspects]);

  const updateAspect = useCallback((aspectId: number, updates: Partial<AspectData>) => {
    setAllAspects(previousAspects => {
      const nextAspects = previousAspects.map(aspect =>
        aspect.id === aspectId
          ? { ...aspect, ...updates }
          : aspect,
      );

      if (initData) {
        aspectsCache.set(nextAspects, initData, cacheKey ?? null);
      }

      return nextAspects;
    });
  }, [initData, cacheKey]);

  return {
    allAspects,
    loading,
    error,
    refetch,
    updateAspect,
  };
};
