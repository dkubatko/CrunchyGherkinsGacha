import { useState, useEffect, useCallback } from 'react';
import { ApiService } from '../services/api';
import { TelegramUtils } from '../utils/telegram';

interface SlotSymbol {
  id: number;
  iconb64?: string;
  displayName?: string;
  type: 'user' | 'character' | 'claim';
}

interface UserSpinsData {
  count: number;
  loading: boolean;
  error: string | null;
}

interface UseSlotsResult {
  symbols: SlotSymbol[];
  spins: UserSpinsData;
  loading: boolean;
  error: string | null;
  refetchSpins: () => Promise<void>;
}

export const useSlots = (chatId?: string, userId?: number): UseSlotsResult => {
  const [symbols, setSymbols] = useState<SlotSymbol[]>([]);
  const [spins, setSpins] = useState<UserSpinsData>({
    count: 0,
    loading: true,
    error: null
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSpins = useCallback(async () => {
    if (!chatId || !userId) {
      setSpins(prev => ({ ...prev, loading: false, error: 'Missing chat ID or user ID' }));
      return;
    }

    try {
      setSpins(prev => ({ ...prev, loading: true, error: null }));

      const initData = TelegramUtils.getInitData();
      if (!initData) {
        throw new Error('No Telegram init data found');
      }

      const spinsData = await ApiService.getUserSpins(userId, chatId, initData);
      setSpins({ count: spinsData.spins, loading: false, error: null });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load spins';
      setSpins({ count: 0, loading: false, error: errorMessage });
    }
  }, [chatId, userId]);

  const refetchSpins = async () => {
    await fetchSpins();
  };

  useEffect(() => {
    const fetchSlotsData = async () => {
      if (!chatId) {
        setError('No chat ID provided');
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);

        const initData = TelegramUtils.getInitData();
        if (!initData) {
          throw new Error('No Telegram init data found');
        }

        // Fetch symbols and spins in parallel
        const [symbolsData] = await Promise.all([
          ApiService.fetchSlotSymbols(chatId, initData),
          userId ? fetchSpins() : Promise.resolve()
        ]);
        
        // Convert to symbols and ensure we have at least 3 for the slot machine
        const convertedSymbols: SlotSymbol[] = symbolsData
          .filter(item => item.slot_iconb64) // Only use items with icons
          .map(item => ({
            id: item.id,
            iconb64: item.slot_iconb64 || undefined,
            displayName: item.display_name || `${item.type} ${item.id}`,
            type: item.type
          }));

        // If we have less than 3 symbols, duplicate them to ensure we have enough
        while (convertedSymbols.length < 3) {
          convertedSymbols.push(...convertedSymbols.slice(0, Math.min(3 - convertedSymbols.length, convertedSymbols.length)));
        }

        setSymbols(convertedSymbols);
        
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred';
        setError(errorMessage);
      } finally {
        setLoading(false);
      }
    };

    fetchSlotsData();
  }, [chatId, userId, fetchSpins]);

  return {
    symbols,
    spins,
    loading,
    error,
    refetchSpins
  };
};