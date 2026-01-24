import { useState, useEffect, useRef, useCallback } from 'react';
import type { CardData } from '@/types';
import { ApiService } from '@/services/api';

interface UseCollectionCardsOptions {
  initialIsOwnCollection: boolean;
  initialEnableTrade: boolean;
  currentUserId: number;
}

interface UseCollectionCardsResult {
  cards: CardData[];
  loading: boolean;
  error: string | null;
  targetUserId: number;
  isOwnCollection: boolean;
  enableTrade: boolean;
  collectionDisplayName: string | null;
  collectionUsername: string | null;
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
  const [cards, setCards] = useState<CardData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [targetUserId, setTargetUserId] = useState(initialTargetUserId);
  const [isOwnCollection, setIsOwnCollection] = useState(options.initialIsOwnCollection);
  const [enableTrade, setEnableTrade] = useState(options.initialEnableTrade);
  const [collectionDisplayName, setCollectionDisplayName] = useState<string | null>(null);
  const [collectionUsername, setCollectionUsername] = useState<string | null>(null);
  const initializationStartedRef = useRef(false);

  const fetchCards = useCallback(async () => {
    try {
      const userCardsResponse = await ApiService.fetchUserCards(
        targetUserId,
        initData,
        chatId ?? undefined
      );
      setCards(userCardsResponse.cards);

      const responseUserId = userCardsResponse.user.user_id;
      const responseUsername = userCardsResponse.user.username ?? null;
      const responseDisplayName = userCardsResponse.user.display_name ?? null;
      const isOwn = responseUserId === options.currentUserId;

      setTargetUserId(responseUserId);
      setCollectionUsername(responseUsername);
      setCollectionDisplayName(responseDisplayName);
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
    collectionDisplayName,
    collectionUsername,
    refetch,
    updateCard
  };
};
