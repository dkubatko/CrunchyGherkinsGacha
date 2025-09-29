import { useState, useEffect } from 'react';
import { ApiService } from '../services/api';
import { TelegramUtils } from '../utils/telegram';

interface SlotSymbol {
  id: number;
  iconb64?: string;
  displayName?: string;
  type: 'user' | 'character';
}

interface UseSlotsResult {
  symbols: SlotSymbol[];
  loading: boolean;
  error: string | null;
}

export const useSlots = (chatId?: string): UseSlotsResult => {
  const [symbols, setSymbols] = useState<SlotSymbol[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

        const data = await ApiService.fetchChatUsersAndCharacters(chatId, initData);
        
        // Convert to symbols and ensure we have at least 3 for the slot machine
        const convertedSymbols: SlotSymbol[] = data
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
  }, [chatId]);

  return {
    symbols,
    loading,
    error
  };
};