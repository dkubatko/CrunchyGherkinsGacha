import { useState, useEffect, useCallback } from 'react';
import type { CardData } from '../types';
import { ApiService } from '../services/api';
import { cardsCache } from '../lib/cardsCache';

interface UseAllCardsResult {
  allCards: CardData[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export const useAllCards = (authToken: string | null): UseAllCardsResult => {
  // Initialize with cached data if available
  const initialCachedCards = authToken ? cardsCache.get(authToken) : null;
  
  const [allCards, setAllCards] = useState<CardData[]>(initialCachedCards || []);
  const [loading, setLoading] = useState(!initialCachedCards);
  const [error, setError] = useState<string | null>(null);

  const fetchAllCards = useCallback(async (forceRefresh = false) => {
    if (!authToken) {
      setError("No authentication token available");
      setLoading(false);
      return;
    }

    // Try to get from cache first (unless forcing refresh)
    if (!forceRefresh) {
      const cachedCards = cardsCache.get(authToken);
      if (cachedCards) {
        setAllCards(cachedCards);
        setLoading(false);
        setError(null);
        return;
      }
    }

    setLoading(true);
    setError(null);

    try {
      const cards = await ApiService.fetchAllCards(authToken);
      cardsCache.set(cards, authToken);
      setAllCards(cards);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch all cards';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, [authToken]);

  useEffect(() => {
    fetchAllCards();
  }, [fetchAllCards]);

  const refetch = useCallback(() => {
    fetchAllCards(true);
  }, [fetchAllCards]);

  return {
    allCards,
    loading,
    error,
    refetch
  };
};