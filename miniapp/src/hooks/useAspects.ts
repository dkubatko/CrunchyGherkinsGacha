import { useState, useCallback, useEffect, useRef } from 'react';
import { ApiService } from '@/services/api';
import type { AspectData } from '@/types';

interface UseAspectsResult {
  aspects: AspectData[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export const useAspects = (
  initData: string,
  chatId: string | null,
  userId?: number,
): UseAspectsResult => {
  const [aspects, setAspects] = useState<AspectData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fetchedRef = useRef(false);

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
    if (fetchedRef.current) return;
    fetchedRef.current = true;
    void fetchAspects();
  }, [fetchAspects]);

  // Silent refetch — doesn't trigger loading state, so modals stay mounted
  const refetch = useCallback(async () => {
    await fetchAspects(true);
  }, [fetchAspects]);

  return { aspects, loading, error, refetch };
};
