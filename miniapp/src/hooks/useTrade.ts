import { useState, useEffect, useCallback } from 'react';
import { ApiService } from '@/services/api';
import { TelegramUtils } from '@/utils/telegram';
import type { TradeOffer, TradeOfferType } from '@/types';

/**
 * Fetches trade options (cards or aspects) for a given trade offer.
 * Generic over the item type to avoid duplicating fetch/refetch/error logic.
 */
export function useTradeOptions<T>(
  tradeOffer: TradeOffer | null | undefined,
  initData: string,
  wantType: 'card' | 'aspect',
) {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchItems = useCallback(
    (offerType: string, offerId: number, init: string) =>
      wantType === 'card'
        ? ApiService.fetchTradeCards(offerType, offerId, init)
        : ApiService.fetchTradeAspects(offerType, offerId, init),
    [wantType],
  );

  useEffect(() => {
    if (!tradeOffer || !initData) {
      setItems([]);
      return;
    }
    setLoading(true);
    setError(null);
    fetchItems(tradeOffer.type, tradeOffer.id, initData)
      .then(result => setItems(result as T[]))
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to fetch trade options'))
      .finally(() => setLoading(false));
  }, [tradeOffer, initData, fetchItems]);

  const refetch = useCallback(async () => {
    if (!tradeOffer || !initData) return;
    try {
      const result = await fetchItems(tradeOffer.type, tradeOffer.id, initData);
      setItems(result as T[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch trade options');
    }
  }, [tradeOffer, initData, fetchItems]);

  return { items, loading, error, refetch };
}

/**
 * Manages trade execution state: loading indicator, API call, close-on-success.
 */
export function useTradeExecution(
  tradeOffer: TradeOffer | null | undefined,
  initData: string,
  wantType: TradeOfferType,
  wantId: number | null,
) {
  const [executing, setExecuting] = useState(false);

  const execute = useCallback(() => {
    if (!tradeOffer || wantId == null) return;
    setExecuting(true);
    const run = async () => {
      try {
        await ApiService.executeTrade(tradeOffer.type, tradeOffer.id, wantType, wantId, initData);
        TelegramUtils.closeApp();
      } catch (err) {
        setExecuting(false);
        const msg = err instanceof Error ? err.message : 'Trade request failed';
        TelegramUtils.showAlert(msg);
      }
    };
    void run();
  }, [tradeOffer, wantType, wantId, initData]);

  return { executing, execute };
}
