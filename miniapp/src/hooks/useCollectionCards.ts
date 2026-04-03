import { useState, useEffect, useRef, useCallback } from 'react';
import type { CardData } from '@/types';
import { ApiService } from '@/services/api';

interface UseCollectionCardsOptions {
  initialIsOwnCollection: boolean;
  initialEnableTrade: boolean;
  currentUserId: number;
  /** Pre-fetched cards from the splash screen — skips the initial API call */
  initialCards?: CardData[];
}

interface UseCollectionCardsResult {
  cards: CardData[];
  loading: boolean;
  error: string | null;
  targetUserId: number;
  isOwnCollection: boolean;
  enableTrade: boolean;
  refetch: () => Promise<void>;
  updateCard: (cardId: number, updates: Partial<CardData>) => void;
}

/**
 * Hook for fetching and managing collection cards.
 * Separated from useCards to avoid coupling with Telegram initialization.
 */
export const useCollectionCards = (
  initialTargetUserId: number,
  chatId: string | null,
  initData: string,
  options: UseCollectionCardsOptions
): UseCollectionCardsResult => {
  const hasInitialCards = Boolean(options.initialCards);
  const [cards, setCards] = useState<CardData[]>(options.initialCards ?? []);
  const [loading, setLoading] = useState(!hasInitialCards);
  const [error, setError] = useState<string | null>(null);
  const [targetUserId, setTargetUserId] = useState(initialTargetUserId);
  const [isOwnCollection, setIsOwnCollection] = useState(options.initialIsOwnCollection);
  const [enableTrade, setEnableTrade] = useState(options.initialEnableTrade);
  const initializationStartedRef = useRef(hasInitialCards);

  const fetchCards = useCallback(async () => {
    try {
      const userCardsResponse = await ApiService.fetchUserCards(
        targetUserId,
        initData,
        chatId ?? undefined
      );
      setCards(userCardsResponse.cards);

      const responseUserId = userCardsResponse.user_id;
      const isOwn = responseUserId === options.currentUserId;

      setTargetUserId(responseUserId);
      setIsOwnCollection(isOwn);
      setEnableTrade(isOwn);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred';
      setError(errorMessage);
    }
  }, [targetUserId, initData, chatId, options.currentUserId]);

  const refetch = useCallback(async () => {
    try {
      await fetchCards();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred';
      setError(errorMessage);
    }
  }, [fetchCards]);

  const updateCard = useCallback((cardId: number, updates: Partial<CardData>) => {
    setCards(previousCards =>
      previousCards.map(card =>
        card.id === cardId
          ? {
              ...card,
              ...updates
            }
          : card
      )
    );
  }, []);

  useEffect(() => {
    if (initializationStartedRef.current) {
      return;
    }
    initializationStartedRef.current = true;

    const initializeAndFetch = async () => {
      try {
        await fetchCards();
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred';
        setError(errorMessage);
      } finally {
        setLoading(false);
      }
    };

    initializeAndFetch();
  }, [fetchCards]);

  return {
    cards,
    loading,
    error,
    targetUserId,
    isOwnCollection,
    enableTrade,
    refetch,
    updateCard
  };
};
