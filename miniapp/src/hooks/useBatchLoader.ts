import { useState, useEffect, useMemo, useRef, useCallback, useReducer } from 'react';
import { imageCache } from '../lib/imageCache';
import type { CardData } from '../types';

interface UseBatchLoaderReturn {
  loadingCards: Set<number>;
  failedCards: Set<number>;
  visibleCardIds: Set<number>;
  setCardVisible: (cardId: number, isVisible: boolean) => void;
}

interface CardImageResponse {
  card_id: number;
  image_b64: string;
}

const BATCH_SIZE = 3;

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

  // Track which cards we've already attempted to load to prevent re-processing
  const processedCardsRef = useRef(new Set<number>());
  
  // Track visible cards
  const [visibleCardIds, setVisibleCardIds] = useState<Set<number>>(new Set());
  
  // Pending batch processing
  const pendingCardsRef = useRef(new Set<number>());

  // Create stable card IDs string for effect dependencies
  const cardIdsString = useMemo(() => cards.map(c => c.id).join(','), [cards]);

  const apiBaseUrl = useMemo(
    () => import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com',
    []
  );

  const markCardsAsProcessing = useCallback((cardsToLoad: CardData[]) => {
    cardsToLoad.forEach(card => {
      processedCardsRef.current.add(card.id);
    });
  }, []);

  const fetchBatchImages = useCallback(
    async (batch: CardData[]) => {
      const response = await fetch(`${apiBaseUrl}/cards/images`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `tma ${initData}`,
        },
        body: JSON.stringify({
          card_ids: batch.map(c => c.id),
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch batch images: ${response.statusText}`);
      }

      const imageResponses: CardImageResponse[] = await response.json();
      imageResponses.forEach(imageResponse => {
    imageCache.set(imageResponse.card_id, imageResponse.image_b64, 'thumb');
      });

      const batchCardIds = batch.map(c => c.id);
      const loadedCardIds = new Set(imageResponses.map(r => r.card_id));
      const failedCardIds = batchCardIds.filter(id => !loadedCardIds.has(id));

      return { batchCardIds, failedCardIds };
    },
    [apiBaseUrl, initData]
  );

  const loadCardsInBatches = useCallback((cardsToLoad: CardData[]) => {
    if (!initData || cardsToLoad.length === 0) return;
    
    console.log(`Loading ${cardsToLoad.length} cards in batches...`);
    
    markCardsAsProcessing(cardsToLoad);
    const allCardIds = cardsToLoad.map(c => c.id);
    dispatch({ type: 'start-loading', ids: allCardIds });

    const processBatches = async () => {
      for (let i = 0; i < cardsToLoad.length; i += BATCH_SIZE) {
        const batch = cardsToLoad.slice(i, i + BATCH_SIZE);

        try {
          console.log(`Loading batch: ${batch.map(c => c.id)}`);
          const { batchCardIds, failedCardIds } = await fetchBatchImages(batch);
          console.log(`Successfully loaded ${batchCardIds.length - failedCardIds.length} images from batch`);

          dispatch({
            type: 'complete-loading',
            completedIds: batchCardIds,
            failedIds: failedCardIds,
          });
        } catch (error) {
          console.error(`Error loading batch:`, error);

          const batchCardIds = batch.map(c => c.id);
          dispatch({ type: 'fail-loading', ids: batchCardIds });
        }

        if (i + BATCH_SIZE < cardsToLoad.length) {
          await new Promise(resolve => setTimeout(resolve, 300));
        }
      }
    };

    void processBatches();
  }, [fetchBatchImages, initData, markCardsAsProcessing]);

  // Process pending cards in batches
  const processPendingBatch = useCallback(() => {
    if (pendingCardsRef.current.size === 0) return;

    const pendingCardIds = Array.from(pendingCardsRef.current);
    const visibleCards = cards.filter(card => 
      pendingCardIds.includes(card.id) && 
  !imageCache.has(card.id, 'thumb') && 
      !processedCardsRef.current.has(card.id)
    );

    if (visibleCards.length > 0) {
      console.log(`Processing pending batch of ${visibleCards.length} cards:`, visibleCards.map(c => c.id));
      loadCardsInBatches(visibleCards);
    }

    // Clear pending cards
    pendingCardsRef.current.clear();
  }, [cards, loadCardsInBatches]);

  // Add card to pending batch and schedule processing
  const addToPendingBatch = useCallback((cardId: number) => {
    pendingCardsRef.current.add(cardId);

    if (pendingCardsRef.current.size >= BATCH_SIZE) {
      console.log(`Pending batch reached ${BATCH_SIZE} cards, processing immediately`);
    }

    processPendingBatch();
  }, [processPendingBatch]);

  // Function to be called by individual cards when visibility changes
  const setCardVisible = useCallback((cardId: number, isVisible: boolean) => {
    setVisibleCardIds(prev => {
      const newSet = new Set(prev);
      if (isVisible) {
        if (!newSet.has(cardId)) {
          console.log(`Card ${cardId} became visible`);
          newSet.add(cardId);
          
          // Add to pending batch if not already cached/processed
          if (!imageCache.has(cardId, 'thumb') && !processedCardsRef.current.has(cardId)) {
            addToPendingBatch(cardId);
          }
        }
      } else {
        newSet.delete(cardId);
      }
      return newSet;
    });
  }, [addToPendingBatch]);

  // If the remaining unfetched cards are fewer than the batch size, load them immediately.
  useEffect(() => {
    if (!cards.length || !initData) return;

    const remainingCards = cards.filter(card =>
      !imageCache.has(card.id, 'thumb') &&
      !processedCardsRef.current.has(card.id)
    );

    if (remainingCards.length > 0 && remainingCards.length < BATCH_SIZE) {
      console.log('Loading remaining cards directly:', remainingCards.map(card => card.id));
      loadCardsInBatches(remainingCards);
    }
  }, [cards, initData, loadCardsInBatches]);

  // Reset state when cards change significantly
  useEffect(() => {
    dispatch({ type: 'reset' });
    processedCardsRef.current.clear();
    pendingCardsRef.current.clear();
    setVisibleCardIds(new Set());
  }, [cardIdsString]);

  return {
    loadingCards: state.loadingCards,
    failedCards: state.failedCards,
    visibleCardIds,
    setCardVisible,
  };
};