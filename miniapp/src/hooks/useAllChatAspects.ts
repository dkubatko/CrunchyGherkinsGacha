import { useState, useEffect, useCallback } from 'react';
import type { AspectData } from '../types';
import { ApiService } from '../services/api';

interface UseAllChatAspectsResult {
  allAspects: AspectData[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

interface UseAllChatAspectsOptions {
  enabled?: boolean;
}

export const useAllChatAspects = (
  initData: string | null,
  aspectId: number | null,
  { enabled = true }: UseAllChatAspectsOptions = {}
): UseAllChatAspectsResult => {
  const [allAspects, setAllAspects] = useState<AspectData[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAspects = useCallback(async () => {
    if (!enabled || !initData || aspectId === null) {
      setAllAspects([]);
      setLoading(false);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const aspects = await ApiService.fetchAspectTradeOptions(aspectId, initData);
      setAllAspects(aspects);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch trade options';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, [enabled, initData, aspectId]);

  useEffect(() => {
    void fetchAspects();
  }, [fetchAspects]);

  const refetch = useCallback(async () => {
    await fetchAspects();
  }, [fetchAspects]);

  return { allAspects, loading, error, refetch };
};
