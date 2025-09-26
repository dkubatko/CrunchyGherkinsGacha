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
  registerCard: (cardId: number, element: Element | null) => void;
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
  
  // Track visible cards and their elements
  const visibleCardsRef = useRef(new Set<number>());
  const cardElementsRef = useRef(new Map<number, Element>());
  const observerRef = useRef<IntersectionObserver | null>(null);

  // Create stable card IDs string for effect dependencies
  const cardIdsString = useMemo(() => cards.map(c => c.id).join(','), [cards]);

  const loadCardsInBatches = useCallback((cardsToLoad: CardData[]) => {
    if (!initData || cardsToLoad.length === 0) return;
    
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

  // Initialize intersection observer
  useEffect(() => {
    if (!('IntersectionObserver' in window)) {
      // Fallback for browsers without IntersectionObserver
      // Load all cards immediately
      console.log('IntersectionObserver not supported, loading all cards');
      const allCardIds = cards.map(c => c.id);
      visibleCardsRef.current = new Set(allCardIds);
      
      // Trigger immediate loading
      setTimeout(() => {
        const cardsToLoad = cards.filter(card => 
          !imageCache.has(card.id) && !processedCardsRef.current.has(card.id)
        );
        
        if (cardsToLoad.length > 0) {
          console.log(`Fallback: Loading ${cardsToLoad.length} cards immediately`);
          loadCardsInBatches(cardsToLoad);
        }
      }, 100);
      
      return;
    }

    observerRef.current = new IntersectionObserver(
      (entries) => {
        let hasNewVisibleCards = false;
        
        entries.forEach((entry) => {
          const cardId = parseInt(entry.target.getAttribute('data-card-id') || '0');
          if (cardId) {
            if (entry.isIntersecting) {
              if (!visibleCardsRef.current.has(cardId)) {
                console.log(`Card ${cardId} became visible`);
                visibleCardsRef.current.add(cardId);
                hasNewVisibleCards = true;
              }
            } else {
              visibleCardsRef.current.delete(cardId);
            }
          }
        });

        // Trigger loading for newly visible cards
        if (hasNewVisibleCards && initData && cards.length > 0) {
          console.log(`${visibleCardsRef.current.size} cards visible, checking what needs loading...`);
          
          const visibleCardsNeedingLoad = cards.filter(card => {
            return visibleCardsRef.current.has(card.id) &&
                   !imageCache.has(card.id) && 
                   !processedCardsRef.current.has(card.id);
          });

          if (visibleCardsNeedingLoad.length > 0) {
            console.log(`Loading ${visibleCardsNeedingLoad.length} visible cards in batches...`);
            loadCardsInBatches(visibleCardsNeedingLoad);
          }
        }
      },
      {
        rootMargin: '200px', // Increased margin to load images earlier
        threshold: 0.1,
      }
    );

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
      }
    };
  }, [initData, cards, loadCardsInBatches]);

  // Fallback: Load first batch immediately after a delay to ensure something loads
  useEffect(() => {
    if (!cards.length || !initData) return;

    const fallbackTimer = setTimeout(() => {
      const cardsNeedingLoad = cards.filter(card => 
        !imageCache.has(card.id) && !processedCardsRef.current.has(card.id)
      );
      
      if (cardsNeedingLoad.length > 0 && visibleCardsRef.current.size === 0) {
        console.log('Fallback: No visible cards detected, loading first batch anyway');
        const firstBatch = cardsNeedingLoad.slice(0, 6); // Load first 6 cards as fallback
        loadCardsInBatches(firstBatch);
      }
    }, 2000); // Wait 2 seconds

    return () => clearTimeout(fallbackTimer);
  }, [cards, initData, loadCardsInBatches]);

  // Register a card element for intersection observation
  const registerCard = useCallback((cardId: number, element: Element | null) => {
    if (!observerRef.current) return;

    // Unobserve previous element if it exists
    const previousElement = cardElementsRef.current.get(cardId);
    if (previousElement) {
      observerRef.current.unobserve(previousElement);
    }

    if (element) {
      // Set data attribute for identification
      element.setAttribute('data-card-id', cardId.toString());
      cardElementsRef.current.set(cardId, element);
      observerRef.current.observe(element);
    } else {
      cardElementsRef.current.delete(cardId);
      visibleCardsRef.current.delete(cardId);
    }
  }, []);

  // Reset state when cards change significantly
  useEffect(() => {
    setState({
      loadingCards: new Set(),
      failedCards: new Set(),
    });
    processedCardsRef.current.clear();
    visibleCardsRef.current.clear();
    
    // Clear all observed elements
    if (observerRef.current) {
      observerRef.current.disconnect();
    }
    cardElementsRef.current.clear();
  }, [cardIdsString]);

  return {
    loadingCards: state.loadingCards,
    failedCards: state.failedCards,
    registerCard,
  };
};