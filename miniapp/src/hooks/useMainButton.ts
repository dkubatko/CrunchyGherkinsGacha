import { useEffect, useState, useRef } from 'react';
import { TelegramUtils } from '../utils/telegram';
import type { View, CardData } from '../types';

export const useMainButton = (
  loading: boolean,
  error: string | null,
  isOwnCollection: boolean,
  enableTrade: boolean,
  hasCards: boolean,
  view: View,
  isGridView: boolean,
  selectedCardForTrade?: CardData | null,
  modalCard?: CardData | null,
  onTradeClick?: () => void,
  onSelectClick?: () => void
) => {
  const [isMainButtonVisible, setIsMainButtonVisible] = useState(false);
  
  // Use refs to store current callback functions to avoid dependency issues
  const onTradeClickRef = useRef(onTradeClick);
  const onSelectClickRef = useRef(onSelectClick);
  
  // Update refs when callbacks change
  onTradeClickRef.current = onTradeClick;
  onSelectClickRef.current = onSelectClick;

  useEffect(() => {
    if (!loading && !error) {
      // Show Trade button in current view for own collection (only if trading is enabled)
      // Allow in gallery view always, or in grid view when a modal card is open
      if (isOwnCollection && enableTrade && hasCards && view === 'current' && !selectedCardForTrade && (!isGridView || modalCard)) {
        setIsMainButtonVisible(true);
        const cleanup = TelegramUtils.setupMainButton(
          'Trade',
          () => onTradeClickRef.current?.()
        );
        return cleanup;
      }
      // Show Select button in modal when trading and viewing others' cards (only if trading is enabled)
      else if (enableTrade && selectedCardForTrade && modalCard && view === 'all' && modalCard.owner && modalCard.owner !== TelegramUtils.getCurrentUsername()) {
        setIsMainButtonVisible(true);
        const cleanup = TelegramUtils.setupMainButton(
          'Select',
          () => onSelectClickRef.current?.()
        );
        return cleanup;
      }
      else {
        setIsMainButtonVisible(false);
        return TelegramUtils.hideMainButton();
      }
    } else {
      // Hide the button if loading or error
      setIsMainButtonVisible(false);
      return TelegramUtils.hideMainButton();
    }
  }, [loading, error, isOwnCollection, enableTrade, hasCards, view, isGridView, selectedCardForTrade, modalCard]);

  return { isMainButtonVisible };
};