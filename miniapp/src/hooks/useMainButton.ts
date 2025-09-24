import { useEffect, useState, useRef } from 'react';
import { TelegramUtils } from '../utils/telegram';
import type { View, CardData } from '../types';

export const useMainButton = (
  loading: boolean,
  error: string | null,
  isOwnCollection: boolean,
  hasCards: boolean,
  view: View,
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
      // Show Trade button in current view for own collection
      if (isOwnCollection && hasCards && view === 'current' && !selectedCardForTrade) {
        setIsMainButtonVisible(true);
        const cleanup = TelegramUtils.setupMainButton(
          'Trade',
          () => onTradeClickRef.current?.()
        );
        return cleanup;
      }
      // Show Select button in modal when trading and viewing others' cards
      else if (selectedCardForTrade && modalCard && view === 'all' && modalCard.owner && modalCard.owner !== TelegramUtils.getCurrentUsername()) {
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
  }, [loading, error, isOwnCollection, hasCards, view, selectedCardForTrade, modalCard]);

  return { isMainButtonVisible };
};