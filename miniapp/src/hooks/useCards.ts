import { useState, useEffect } from 'react';
import type { CardData, UserData } from '../types';
import { ApiService } from '../services/api';
import { TelegramUtils } from '../utils/telegram';

interface UseCardsResult {
  cards: CardData[];
  loading: boolean;
  error: string | null;
  userData: UserData | null;
  authToken: string | null;
}

export const useCards = (): UseCardsResult => {
  const [cards, setCards] = useState<CardData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [userData, setUserData] = useState<UserData | null>(null);
  const [authToken, setAuthToken] = useState<string | null>(null);

  useEffect(() => {
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

        // Get auth token
        const token = TelegramUtils.getAuthToken();
        if (!token) {
          setError("No authentication token found");
          setLoading(false);
          return;
        }
        setAuthToken(token);

        // Fetch user's cards
        const userCards = await ApiService.fetchUserCards(user.username, token);
        setCards(userCards);
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
    authToken
  };
};