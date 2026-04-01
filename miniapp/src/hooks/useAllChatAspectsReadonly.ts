import { useState, useEffect, useCallback, useRef } from 'react';
import type { AspectData } from '../types';
import { ApiService } from '../services/api';

interface UseAllChatAspectsReadonlyResult {
  allAspects: AspectData[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

interface UseAllChatAspectsReadonlyOptions {
  enabled?: boolean;
}

export const useAllChatAspectsReadonly = (
  initData: string | null,
  chatId: string | null,
  { enabled = true }: UseAllChatAspectsReadonlyOptions = {}
): UseAllChatAspectsReadonlyResult => {
  const [allAspects, setAllAspects] = useState<AspectData[]>([]);
  const [loading, setLoading] = useState<boolean>(enabled);
  const [error, setError] = useState<string | null>(null);
  const fetchedRef = useRef(false);

  const fetchAllAspects = useCallback(
    async (force = false) => {
      if (!enabled || !initData || !chatId) {
        setLoading(false);
        return;
      }

      if (!force && fetchedRef.current) return;

      setLoading(true);
      setError(null);

      try {
        const aspects = await ApiService.fetchAllChatAspects(initData, chatId);
        setAllAspects(aspects);
        fetchedRef.current = true;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to fetch all aspects';
        setError(msg);
      } finally {
        setLoading(false);
      }
    },
    [enabled, initData, chatId]
  );

  useEffect(() => {
    void fetchAllAspects();
  }, [fetchAllAspects]);

  const refetch = useCallback(async () => {
    await fetchAllAspects(true);
  }, [fetchAllAspects]);

  return { allAspects, loading, error, refetch };
};
