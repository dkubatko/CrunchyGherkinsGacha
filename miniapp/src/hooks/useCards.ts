import { useState, useEffect, useRef } from 'react';
import type { CardData, UserData } from '../types';
import { ApiService } from '../services/api';
import { TelegramUtils } from '../utils/telegram';

interface UseCardsResult {
  cards: CardData[];
  loading: boolean;
  error: string | null;
  userData: UserData | null;
  initData: string | null;
}

export const useCards = (): UseCardsResult => {
  const [cards, setCards] = useState<CardData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [userData, setUserData] = useState<UserData | null>(null);
  const [initData, setInitData] = useState<string | null>(null);
  const initializationStartedRef = useRef(false);

  useEffect(() => {
    if (initializationStartedRef.current) {
      return;
    }
    initializationStartedRef.current = true;

    const initializeAndFetch = async () => {
      try {
        // Initialize user data
        const user = TelegramUtils.initializeUser();
        if (!user) {
          setError("Failed to initialize user data");
          setLoading(false);
          return;
        }
        setUserData(user);

        // Get init data
        const telegramInitData = TelegramUtils.getInitData();
        if (!telegramInitData) {
          setError("No Telegram init data found");
          setLoading(false);
          return;
        }
        setInitData(telegramInitData);

        const shouldFetchCollection = !user.singleCardView && !user.slotsView;

        if (shouldFetchCollection) {
          const userCardsResponse = await ApiService.fetchUserCards(
            user.targetUserId,
            telegramInitData,
            user.chatId ?? undefined
          );
          setCards(userCardsResponse.cards);

          setUserData((previous) => {
            if (!previous) {
              return previous;
            }

            const responseUserId = userCardsResponse.user.user_id;
            const collectionUsername = userCardsResponse.user.username ?? null;
            const collectionDisplayName = userCardsResponse.user.display_name ?? null;
            const isOwn = responseUserId === previous.currentUserId;

            return {
              ...previous,
              targetUserId: responseUserId,
              collectionUsername,
              collectionDisplayName,
              isOwnCollection: isOwn,
              enableTrade: isOwn,
            };
          });
        } else {
          setCards([]);
        }
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred';
        setError(errorMessage);
      } finally {
        setLoading(false);
      }
    };

    initializeAndFetch();
  }, []);

  return {
    cards,
    loading,
    error,
    userData,
    initData
  };
};