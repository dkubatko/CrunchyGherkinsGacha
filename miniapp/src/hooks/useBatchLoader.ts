import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { imageCache } from '../lib/imageCache';
import type { CardData } from '../types';

interface BatchLoadState {
  loadingCards: Set<number>;
  failedCards: Set<number>;
}

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

export const useBatchLoader = (
  cards: CardData[],
  initData: string | null
): UseBatchLoaderReturn => {
  const [state, setState] = useState<BatchLoadState>({
    loadingCards: new Set(),
    failedCards: new Set(),
  });

  // Track which cards we've already attempted to load to prevent re-processing
  const processedCardsRef = useRef(new Set<number>());
  
  // Track visible cards
  const [visibleCardIds, setVisibleCardIds] = useState<Set<number>>(new Set());
  
  // Pending batch processing
  const pendingCardsRef = useRef(new Set<number>());
  const batchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Create stable card IDs string for effect dependencies
  const cardIdsString = useMemo(() => cards.map(c => c.id).join(','), [cards]);

  const loadCardsInBatches = useCallback((cardsToLoad: CardData[]) => {
    if (!initData || cardsToLoad.length === 0) return;
    
    console.log(`Loading ${cardsToLoad.length} cards in batches...`);
    
    // Mark cards as being processed to prevent re-processing
    cardsToLoad.forEach(card => {
      processedCardsRef.current.add(card.id);
    });

    // Mark cards as loading
    setState(prev => ({
      ...prev,
      loadingCards: new Set([...prev.loadingCards, ...cardsToLoad.map(c => c.id)]),
    }));

    // Process batches
    const processBatches = async () => {
      for (let i = 0; i < cardsToLoad.length; i += BATCH_SIZE) {
        const batch = cardsToLoad.slice(i, i + BATCH_SIZE);
        
        try {
          console.log(`Loading batch: ${batch.map(c => c.id)}`);
          const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com';
          
          const response = await fetch(`${apiBaseUrl}/cards/images`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `tma ${initData}`
            },
            body: JSON.stringify({
              card_ids: batch.map(c => c.id)
            })
          });
          
          if (!response.ok) {
            throw new Error(`Failed to fetch batch images: ${response.statusText}`);
          }
          
          const imageResponses: CardImageResponse[] = await response.json();
          console.log(`Successfully loaded ${imageResponses.length} images from batch`);
          
          // Cache the loaded images
          for (const imageResponse of imageResponses) {
            imageCache.set(imageResponse.card_id, imageResponse.image_b64);
          }

          // Update state: remove from loading, add failures to failed
          const batchCardIds = batch.map(c => c.id);
          const loadedCardIds = new Set(imageResponses.map(r => r.card_id));
          const failedCardIds = batchCardIds.filter(id => !loadedCardIds.has(id));

          setState(prev => ({
            loadingCards: new Set([...prev.loadingCards].filter(id => !batchCardIds.includes(id))),
            failedCards: new Set([...prev.failedCards, ...failedCardIds]),
          }));

        } catch (error) {
          console.error(`Error loading batch:`, error);
          
          const batchCardIds = batch.map(c => c.id);
          
          // Mark all cards in this batch as failed
          setState(prev => ({
            loadingCards: new Set([...prev.loadingCards].filter(id => !batchCardIds.includes(id))),
            failedCards: new Set([...prev.failedCards, ...batchCardIds]),
          }));
        }
        
        // Add a small delay between batches to avoid overwhelming the server
        if (i + BATCH_SIZE < cardsToLoad.length) {
          await new Promise(resolve => setTimeout(resolve, 300));
        }
      }
    };

    processBatches();
  }, [initData]);

  // Process pending cards in batches
  const processPendingBatch = useCallback(() => {
    if (pendingCardsRef.current.size === 0) return;

    const pendingCardIds = Array.from(pendingCardsRef.current);
    const visibleCards = cards.filter(card => 
      pendingCardIds.includes(card.id) && 
      !imageCache.has(card.id) && 
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
    
    // Clear existing timeout
    if (batchTimeoutRef.current) {
      clearTimeout(batchTimeoutRef.current);
    }
    
    // If we have enough for a batch, process immediately
    if (pendingCardsRef.current.size >= BATCH_SIZE) {
      console.log(`Pending batch reached ${BATCH_SIZE} cards, processing immediately`);
      processPendingBatch();
    } else {
      // Otherwise, wait a bit to accumulate more cards
      batchTimeoutRef.current = setTimeout(() => {
        console.log(`Processing pending batch after timeout (${pendingCardsRef.current.size} cards)`);
        processPendingBatch();
      }, 200); // Wait 200ms to accumulate more cards
    }
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
          if (!imageCache.has(cardId) && !processedCardsRef.current.has(cardId)) {
            addToPendingBatch(cardId);
          }
        }
      } else {
        newSet.delete(cardId);
      }
      return newSet;
    });
  }, [addToPendingBatch]);

  // Fallback: Load first batch after 1 second if nothing loaded
  useEffect(() => {
    if (!cards.length || !initData) return;

    const fallbackTimer = setTimeout(() => {
      const cardsNeedingLoad = cards.filter(card => 
        !imageCache.has(card.id) && !processedCardsRef.current.has(card.id)
      );
      
      if (cardsNeedingLoad.length > 0) {
        console.log('Fallback: Loading first 6 cards after 1 second timeout');
        const firstBatch = cardsNeedingLoad.slice(0, 6);
        loadCardsInBatches(firstBatch);
      }
    }, 1000);

    return () => {
      clearTimeout(fallbackTimer);
      if (batchTimeoutRef.current) {
        clearTimeout(batchTimeoutRef.current);
      }
    };
  }, [cards, initData, loadCardsInBatches]);

  // Reset state when cards change significantly
  useEffect(() => {
    setState({
      loadingCards: new Set(),
      failedCards: new Set(),
    });
    processedCardsRef.current.clear();
    pendingCardsRef.current.clear();
    setVisibleCardIds(new Set());
    
    // Clear any pending timeouts
    if (batchTimeoutRef.current) {
      clearTimeout(batchTimeoutRef.current);
      batchTimeoutRef.current = null;
    }
  }, [cardIdsString]);

  return {
    loadingCards: state.loadingCards,
    failedCards: state.failedCards,
    visibleCardIds,
    setCardVisible,
  };
};