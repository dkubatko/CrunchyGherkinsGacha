import { useState, useEffect, useRef, useCallback } from 'react';
import type { CardData } from '@/types';
import { ApiService } from '@/services/api';

interface UseCollectionCardsResult {
  cards: CardData[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  updateCard: (cardId: number, updates: Partial<CardData>) => void;
}

/**
 * Hook for fetching and managing collection cards.
 * Ownership resolution is handled by the hub — this hook trusts the caller.
 */
export const useCollectionCards = (
  initData: string,
  chatId: string | null,
  userId?: number,
  options?: { initialCards?: CardData[]; enabled?: boolean },
): UseCollectionCardsResult => {
  const enabled = options?.enabled ?? true;
  const hasInitial = Boolean(options?.initialCards);
  const [cards, setCards] = useState<CardData[]>(options?.initialCards ?? []);
  const [loading, setLoading] = useState(!hasInitial && enabled);
  const [error, setError] = useState<string | null>(null);
  const fetchedRef = useRef(hasInitial);

  const fetchCards = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      setError(null);
      const response = await ApiService.fetchUserCards(
        userId ?? 0,
        initData,
        chatId ?? undefined,
      );
      setCards(response.cards);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch cards';
      setError(message);
      console.error('Failed to fetch cards:', err);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [initData, chatId, userId]);

  useEffect(() => {
    if (!enabled || fetchedRef.current) return;
    fetchedRef.current = true;
    void fetchCards();
  }, [enabled, fetchCards]);

  const refetch = useCallback(async () => {
    await fetchCards(true);
  }, [fetchCards]);

  const updateCard = useCallback((cardId: number, updates: Partial<CardData>) => {
    setCards(prev => prev.map(c => c.id === cardId ? { ...c, ...updates } : c));
  }, []);

  return { cards, loading, error, refetch, updateCard };
};
