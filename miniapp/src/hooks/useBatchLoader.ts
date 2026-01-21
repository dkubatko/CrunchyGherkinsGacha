import { useEffect, useMemo, useRef, useCallback, useReducer } from 'react';
import { imageCache } from '../lib/imageCache';
import type { CardData } from '../types';

interface UseBatchLoaderReturn {
  loadingCards: Set<number>;
  failedCards: Set<number>;
  setCardVisible: (cardId: number, isVisible: boolean) => void;
}

interface CardImageResponse {
  card_id: number;
  image_b64: string;
}

const BATCH_SIZE = 3;  // Backend limit is 3 cards per request
const BATCH_DELAY_MS = 20;  // Small delay between batches
const DEBOUNCE_MS = 16;  // ~1 frame to collect visibility events before processing

interface BatchLoadState {
  loadingCards: Set<number>;
  failedCards: Set<number>;
}

type BatchAction =
  | { type: 'start-loading'; ids: number[] }
  | { type: 'complete-loading'; completedIds: number[]; failedIds: number[] }
  | { type: 'fail-loading'; ids: number[] }
  | { type: 'reset' };

const initialBatchState: BatchLoadState = {
  loadingCards: new Set(),
  failedCards: new Set(),
};

const batchReducer = (state: BatchLoadState, action: BatchAction): BatchLoadState => {
  switch (action.type) {
    case 'start-loading':
      return {
        loadingCards: new Set([...state.loadingCards, ...action.ids]),
        failedCards: new Set(state.failedCards),
      };
    case 'complete-loading': {
      const nextLoading = new Set(state.loadingCards);
      action.completedIds.forEach(id => nextLoading.delete(id));

      const nextFailed = new Set(state.failedCards);
      action.failedIds.forEach(id => nextFailed.add(id));

      return {
        loadingCards: nextLoading,
        failedCards: nextFailed,
      };
    }
    case 'fail-loading': {
      const nextLoading = new Set(state.loadingCards);
      action.ids.forEach(id => nextLoading.delete(id));

      const nextFailed = new Set(state.failedCards);
      action.ids.forEach(id => nextFailed.add(id));

      return {
        loadingCards: nextLoading,
        failedCards: nextFailed,
      };
    }
    case 'reset':
      return {
        loadingCards: new Set(),
        failedCards: new Set(),
      };
    default:
      return state;
  }
};

export const useBatchLoader = (
  cards: CardData[],
  initData: string | null
): UseBatchLoaderReturn => {
  const [state, dispatch] = useReducer(batchReducer, initialBatchState);

  // Persistent set of currently visible card IDs - this is the source of truth
  const visibleCardsRef = useRef(new Set<number>());
  
  // Track cards currently being loaded to avoid duplicate requests
  const loadingCardsRef = useRef(new Set<number>());
  
  // Flag to prevent concurrent batch processing
  const isProcessingRef = useRef(false);
  
  // Timer for the processing loop
  const processTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Create a map of cardId -> image_updated_at for quick lookup
  const cardTimestampsRef = useRef(new Map<number, string | null>());
  
  // Update timestamps map when cards change
  useEffect(() => {
    cardTimestampsRef.current.clear();
    for (const card of cards) {
      cardTimestampsRef.current.set(card.id, card.image_updated_at ?? null);
    }
  }, [cards]);

  // Create stable card IDs string for effect dependencies
  const cardIdsString = useMemo(() => cards.map(c => c.id).join(','), [cards]);

  const apiBaseUrl = useMemo(
    () => import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com',
    []
  );

  // Fetch a single batch of images
  const fetchBatch = useCallback(
    async (cardIds: number[]): Promise<{ loadedIds: number[]; failedIds: number[] }> => {
      try {
        const response = await fetch(`${apiBaseUrl}/cards/images`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `tma ${initData}`,
          },
          body: JSON.stringify({ card_ids: cardIds }),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const imageResponses: CardImageResponse[] = await response.json();
        imageResponses.forEach(r => {
          // Store with the server timestamp for future validation
          const imageUpdatedAt = cardTimestampsRef.current.get(r.card_id) ?? null;
          imageCache.set(r.card_id, r.image_b64, 'thumb', imageUpdatedAt);
        });

        const loadedIds = imageResponses.map(r => r.card_id);
        const failedIds = cardIds.filter(id => !loadedIds.includes(id));
        return { loadedIds, failedIds };
      } catch (error) {
        console.error('Batch fetch error:', error);
        return { loadedIds: [], failedIds: cardIds };
      }
    },
    [apiBaseUrl, initData]
  );

  // Get cards that need loading: visible, not validly cached, not currently loading, not failed
  const getCardsToLoad = useCallback((): number[] => {
    const result: number[] = [];
    for (const cardId of visibleCardsRef.current) {
      const imageUpdatedAt = cardTimestampsRef.current.get(cardId) ?? null;
      
      // Use isValidCached to check both memory and persistent cache with timestamp validation
      if (
        !imageCache.isValidCached(cardId, 'thumb', imageUpdatedAt) &&
        !loadingCardsRef.current.has(cardId) &&
        !state.failedCards.has(cardId)
      ) {
        result.push(cardId);
      }
    }
    return result;
  }, [state.failedCards]);

  // Main processing function - runs continuously while there are cards to load
  const processQueue = useCallback(async () => {
    if (!initData || isProcessingRef.current) return;
    
    const cardsToLoad = getCardsToLoad();
    if (cardsToLoad.length === 0) return;
    
    isProcessingRef.current = true;
    
    // Take the next batch
    const batch = cardsToLoad.slice(0, BATCH_SIZE);
    
    // Mark as loading
    batch.forEach(id => loadingCardsRef.current.add(id));
    dispatch({ type: 'start-loading', ids: batch });
    
    // Fetch the batch
    const { loadedIds, failedIds } = await fetchBatch(batch);
    
    // Update state
    batch.forEach(id => loadingCardsRef.current.delete(id));
    dispatch({ type: 'complete-loading', completedIds: loadedIds, failedIds });
    
    isProcessingRef.current = false;
    
    // Check if there are more cards to load - continue immediately
    const remaining = getCardsToLoad();
    if (remaining.length > 0) {
      // Small delay between batches to avoid overwhelming the server
      processTimerRef.current = setTimeout(() => {
        processTimerRef.current = null;
        void processQueue();
      }, BATCH_DELAY_MS);
    }
  }, [initData, fetchBatch, getCardsToLoad]);

  // Debounce timer for collecting visibility events
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Schedule processing with debounce to collect multiple visibility events
  const scheduleProcessing = useCallback(() => {
    // If already processing, processQueue will pick up new visible cards when it checks remaining
    if (isProcessingRef.current) return;
    // If batch timer is pending, it will process
    if (processTimerRef.current) return;
    // If debounce timer is pending, let it collect more cards
    if (debounceTimerRef.current) return;
    
    // Start debounce timer to collect visibility events
    debounceTimerRef.current = setTimeout(() => {
      debounceTimerRef.current = null;
      void processQueue();
    }, DEBOUNCE_MS);
  }, [processQueue]);

  // Simple visibility callback - just updates the set and schedules processing
  const setCardVisible = useCallback((cardId: number, isVisible: boolean) => {
    if (isVisible) {
      if (!visibleCardsRef.current.has(cardId)) {
        visibleCardsRef.current.add(cardId);
        // Only schedule if this card needs loading (check with timestamp validation)
        const imageUpdatedAt = cardTimestampsRef.current.get(cardId) ?? null;
        if (!imageCache.isValidCached(cardId, 'thumb', imageUpdatedAt) && !loadingCardsRef.current.has(cardId)) {
          scheduleProcessing();
        }
      }
    } else {
      visibleCardsRef.current.delete(cardId);
    }
  }, [scheduleProcessing]);

  // Reset when cards change
  useEffect(() => {
    dispatch({ type: 'reset' });
    visibleCardsRef.current.clear();
    loadingCardsRef.current.clear();
    isProcessingRef.current = false;
    if (processTimerRef.current) {
      clearTimeout(processTimerRef.current);
      processTimerRef.current = null;
    }
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
  }, [cardIdsString]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (processTimerRef.current) {
        clearTimeout(processTimerRef.current);
      }
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  return {
    loadingCards: state.loadingCards,
    failedCards: state.failedCards,
    setCardVisible,
  };
};