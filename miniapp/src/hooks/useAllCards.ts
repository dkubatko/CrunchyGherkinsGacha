import { useState, useEffect, useCallback } from 'react';
import type { CardData } from '../types';
import { ApiService } from '../services/api';
import { cardsCache } from '../lib/cardsCache';

interface UseAllCardsResult {
  allCards: CardData[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  updateCard: (cardId: number, updates: Partial<CardData>) => void;
}

interface UseAllCardsOptions {
  tradeCardId?: number | null;
  enabled?: boolean;
}

export const useAllCards = (
  initData: string | null,
  chatId: string | null = null,
  { tradeCardId = null, enabled = true }: UseAllCardsOptions = {}
): UseAllCardsResult => {
  const cacheKey = tradeCardId !== null ? `trade:${tradeCardId}` : chatId ?? null;
  const initialCachedCards = initData && enabled ? cardsCache.get(initData, cacheKey) : null;

  const [allCards, setAllCards] = useState<CardData[]>(initialCachedCards || []);
  const [loading, setLoading] = useState<boolean>(enabled && !initialCachedCards);
  const [error, setError] = useState<string | null>(null);

  const fetchAllCards = useCallback(
    async (forceRefresh = false) => {
      if (!enabled) {
        setLoading(false);
        setError(null);
        setAllCards([]);
        return;
      }

      if (!initData) {
        setError('No Telegram init data available');
        setLoading(false);
        return;
      }

      if (!forceRefresh) {
        const cachedCards = cardsCache.get(initData, cacheKey ?? null);
        if (cachedCards) {
          setAllCards(cachedCards);
          setLoading(false);
          setError(null);
          return;
        }
        setAllCards([]);
      }

      setLoading(true);
      setError(null);

      try {
        let cards: CardData[];
        if (tradeCardId !== null) {
          cards = await ApiService.fetchTradeOptions(tradeCardId, initData);
        } else {
          cards = await ApiService.fetchAllCards(initData, chatId ?? undefined);
        }
        cardsCache.set(cards, initData, cacheKey ?? null);
        setAllCards(cards);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to fetch all cards';
        setError(errorMessage);
      } finally {
        setLoading(false);
      }
    },
    [enabled, initData, chatId, tradeCardId, cacheKey]
  );

  useEffect(() => {
    fetchAllCards();
  }, [fetchAllCards]);

  const refetch = useCallback(async () => {
    await fetchAllCards(true);
  }, [fetchAllCards]);

  const updateCard = useCallback((cardId: number, updates: Partial<CardData>) => {
    setAllCards(previousCards => {
      const nextCards = previousCards.map(card =>
        card.id === cardId
          ? {
              ...card,
              ...updates
            }
          : card
      );

      if (initData) {
        cardsCache.set(nextCards, initData, cacheKey ?? null);
      }

      return nextCards;
    });
  }, [initData, cacheKey]);

  return {
    allCards,
    loading,
    error,
    refetch,
    updateCard
  };
};