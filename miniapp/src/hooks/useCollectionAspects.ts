import { useState, useCallback, useEffect, useRef } from 'react';
import { ApiService } from '@/services/api';
import type { AspectData } from '@/types';

interface UseAspectsResult {
  aspects: AspectData[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  updateAspect: (aspectId: number, updates: Partial<AspectData>) => void;
  removeAspect: (aspectId: number) => void;
}

export const useCollectionAspects = (
  initData: string,
  chatId: string | null,
  userId?: number,
  options?: { initialAspects?: AspectData[]; enabled?: boolean },
): UseAspectsResult => {
  const enabled = options?.enabled ?? true;
  const hasInitial = Boolean(options?.initialAspects);
  const [aspects, setAspects] = useState<AspectData[]>(options?.initialAspects ?? []);
  const [loading, setLoading] = useState(!hasInitial && enabled);
  const [error, setError] = useState<string | null>(null);
  const fetchedRef = useRef(hasInitial);

  const fetchAspects = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      setError(null);
      const data = await ApiService.fetchUserAspects(initData, chatId, userId);
      setAspects(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch aspects';
      setError(message);
      console.error('Failed to fetch aspects:', err);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [initData, chatId, userId]);

  useEffect(() => {
    if (!enabled || fetchedRef.current) return;
    fetchedRef.current = true;
    void fetchAspects();
  }, [enabled, fetchAspects]);

  // Silent refetch — doesn't trigger loading state, so modals stay mounted
  const refetch = useCallback(async () => {
    await fetchAspects(true);
  }, [fetchAspects]);

  // Client-side update functions (no API calls)
  const updateAspect = useCallback((aspectId: number, updates: Partial<AspectData>) => {
    setAspects(prev => prev.map(a => a.id === aspectId ? { ...a, ...updates } : a));
  }, []);

  const removeAspect = useCallback((aspectId: number) => {
    setAspects(prev => prev.filter(a => a.id !== aspectId));
  }, []);

  return { aspects, loading, error, refetch, updateAspect, removeAspect };
};
