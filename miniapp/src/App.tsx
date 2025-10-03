import { useState, useCallback, useEffect, useRef } from 'react';
import './App.css';

// Components
import Card from './components/Card';
import SingleCardView from './components/SingleCardView';
import AllCards from './components/AllCards';
import CardModal from './components/CardModal';
import FilterSortControls from './components/FilterSortControls';
import ActionPanel from './components/ActionPanel';
import Slots from './components/Slots';
import type { FilterOptions, SortOptions } from './components/FilterSortControls';
import type { ActionButton } from './components/ActionPanel';

// Hooks
import {
  useCards,
  useAllCards,
  useOrientation,
  useModal,
  useSwipeHandlers,
  useSlots
} from './hooks';

// Utils
import { TelegramUtils } from './utils/telegram';

// Services
import { ApiService } from './services/api';

// Lib
import { getIconObjectUrl } from './lib/iconUrlCache';

// Types
import type { CardData, View } from './types';

// Build info
import { BUILD_INFO } from './build-info';

type ClaimBalanceState = {
  balance: number | null;
  loading: boolean;
  error?: string;
};

function App() {
  // Log build info to console for debugging
  console.log('App build info:', BUILD_INFO);
  
  // Viewport height management - lock in the maximum height
  const [lockedViewportHeight, setLockedViewportHeight] = useState<number | null>(null);
  
  // Core data hooks
  const { cards, loading, error, userData, initData } = useCards();
  const { symbols: slotsSymbols, spins: slotsSpins, loading: slotsLoading, error: slotsError, refetchSpins } = useSlots(
    userData?.slotsView && userData.chatId ? userData.chatId : undefined,
    userData?.currentUserId
  );
  const [slotsImagesLoaded, setSlotsImagesLoaded] = useState(false);
  
  // UI state
  const [currentIndex, setCurrentIndex] = useState(0);
  const [view, setView] = useState<View>('current');
  const [selectedCardForTrade, setSelectedCardForTrade] = useState<CardData | null>(null);
  const [isTradeGridActive, setIsTradeGridActive] = useState(false);
  const [isGridView, setIsGridView] = useState(false);
  const [showLockDialog, setShowLockDialog] = useState(false);
  const [lockingCard, setLockingCard] = useState(false);
  const [chatClaimBalances, setChatClaimBalances] = useState<Record<string, ClaimBalanceState>>({});
  const claimBalanceRequestsRef = useRef<Map<string, Promise<number | null>>>(new Map());
  const pendingChatIdsRef = useRef<Set<string>>(new Set());

  // Filter and sort state
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    owner: '',
    rarity: ''
  });
  const [sortOptions, setSortOptions] = useState<SortOptions>({
    field: 'rarity',
    direction: 'desc'
  });
  
  // Current view grid filter and sort state (only rarity filter, but full sort options)
  const [currentGridFilterOptions, setCurrentGridFilterOptions] = useState<FilterOptions>({
    owner: '', // Always empty for current view
    rarity: ''
  });
  const [currentGridSortOptions, setCurrentGridSortOptions] = useState<SortOptions>({
    field: 'rarity',
    direction: 'desc'
  });

  const hasChatScope = Boolean(userData?.chatId);
  const isTradeView = view === 'all' && isTradeGridActive;
  const activeTradeCardId = isTradeView && selectedCardForTrade ? selectedCardForTrade.id : null;
  const cardsScopeChatId = isTradeView && selectedCardForTrade?.chat_id
    ? selectedCardForTrade.chat_id
    : userData?.chatId ?? null;
  const shouldFetchAllCards = !userData?.slotsView && (hasChatScope || activeTradeCardId !== null);

  const ensureClaimBalance = useCallback(async (
    chatId: string,
    options: { force?: boolean } = {}
  ): Promise<number | null> => {
    if (!chatId) {
      return null;
    }

    if (!userData || !initData) {
      pendingChatIdsRef.current.add(chatId);
      return null;
    }

    pendingChatIdsRef.current.delete(chatId);

    const existingState = chatClaimBalances[chatId];
    const fallbackBalance = existingState?.balance ?? null;

    if (!options.force && existingState && fallbackBalance !== null && !existingState.error) {
      return fallbackBalance;
    }

    if (!options.force && claimBalanceRequestsRef.current.has(chatId)) {
      return claimBalanceRequestsRef.current.get(chatId)!;
    }

    const fetchPromise = (async () => {
      setChatClaimBalances(prev => ({
        ...prev,
        [chatId]: {
          balance: prev[chatId]?.balance ?? null,
          loading: true,
          error: undefined
        }
      }));

      try {
        const result = await ApiService.fetchClaimBalance(userData.currentUserId, chatId, initData);
        setChatClaimBalances(prev => ({
          ...prev,
          [chatId]: {
            balance: result.balance,
            loading: false,
            error: undefined
          }
        }));
        return result.balance ?? null;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to fetch claim balance';
        console.error(`Failed to fetch claim balance for chat ${chatId}`, err);
        setChatClaimBalances(prev => ({
          ...prev,
          [chatId]: {
            balance: prev[chatId]?.balance ?? fallbackBalance,
            loading: false,
            error: message
          }
        }));
        return fallbackBalance;
      }
    })();

    claimBalanceRequestsRef.current.set(chatId, fetchPromise);

    const resolvedBalance = await fetchPromise;
    claimBalanceRequestsRef.current.delete(chatId);

    return resolvedBalance;
  }, [chatClaimBalances, initData, userData]);

  const handleCardOpen = useCallback((card: Pick<CardData, 'id' | 'chat_id'>) => {
    if (!card.chat_id) {
      return;
    }

    void ensureClaimBalance(card.chat_id);
  }, [ensureClaimBalance]);

  useEffect(() => {
    if (!userData || !initData || pendingChatIdsRef.current.size === 0) {
      return;
    }

    const queuedChatIds = Array.from(pendingChatIdsRef.current);
    pendingChatIdsRef.current.clear();

    queuedChatIds.forEach(chatId => {
      void ensureClaimBalance(chatId, { force: true });
    });
  }, [ensureClaimBalance, initData, userData]);

  const {
    allCards,
    loading: allCardsLoading,
    error: allCardsError,
    refetch: refetchAllCards
  } = useAllCards(initData, cardsScopeChatId, {
    enabled: shouldFetchAllCards,
    tradeCardId: activeTradeCardId
  });

  const tradeCardName = selectedCardForTrade
    ? `${selectedCardForTrade.modifier} ${selectedCardForTrade.base_name}`
    : null;

  // Filtering and sorting logic
  const applyFiltersAndSorting = (cards: CardData[]) => {
    let filtered = cards;

    // Apply owner filter
    if (filterOptions.owner) {
      filtered = filtered.filter(card => card.owner === filterOptions.owner);
    }

    // Apply rarity filter
    if (filterOptions.rarity) {
      filtered = filtered.filter(card => card.rarity === filterOptions.rarity);
    }

    // Apply sorting
    const sorted = [...filtered].sort((a, b) => {
      let aValue: string | number;
      let bValue: string | number;

      switch (sortOptions.field) {
        case 'rarity': {
          // Define rarity order: Common -> Rare -> Epic -> Legendary
          const rarityOrder = ['Common', 'Rare', 'Epic', 'Legendary'];
          const aIndex = rarityOrder.indexOf(a.rarity);
          const bIndex = rarityOrder.indexOf(b.rarity);
          // If rarity not found in order, put it at the end
          aValue = aIndex === -1 ? rarityOrder.length : aIndex;
          bValue = bIndex === -1 ? rarityOrder.length : bIndex;
          break;
        }
        case 'id':
          aValue = a.id;
          bValue = b.id;
          break;
        case 'name':
          aValue = `${a.modifier} ${a.base_name}`.toLowerCase();
          bValue = `${b.modifier} ${b.base_name}`.toLowerCase();
          break;
        default:
          aValue = a.id;
          bValue = b.id;
      }

      if (typeof aValue === 'string' && typeof bValue === 'string') {
        const comparison = aValue.localeCompare(bValue);
        return sortOptions.direction === 'asc' ? comparison : -comparison;
      } else if (typeof aValue === 'number' && typeof bValue === 'number') {
        const comparison = aValue - bValue;
        return sortOptions.direction === 'asc' ? comparison : -comparison;
      }

      return 0;
    });

    return sorted;
  };

  const baseDisplayedCards = isTradeView && selectedCardForTrade
    ? allCards.filter((card) => card.id !== selectedCardForTrade.id)
    : allCards;

  const displayedCards = applyFiltersAndSorting(baseDisplayedCards);

  // Apply filtering and sorting for current view grid
  const applyCurrentGridFiltersAndSorting = (cards: CardData[]) => {
    let filtered = cards;

    // Apply rarity filter
    if (currentGridFilterOptions.rarity) {
      filtered = filtered.filter(card => card.rarity === currentGridFilterOptions.rarity);
    }

    // Apply sorting
    const sorted = [...filtered].sort((a, b) => {
      let aValue: string | number;
      let bValue: string | number;

      switch (currentGridSortOptions.field) {
        case 'rarity': {
          // Define rarity order: Common -> Rare -> Epic -> Legendary
          const rarityOrder = ['Common', 'Rare', 'Epic', 'Legendary'];
          const aIndex = rarityOrder.indexOf(a.rarity);
          const bIndex = rarityOrder.indexOf(b.rarity);
          // If rarity not found in order, put it at the end
          aValue = aIndex === -1 ? rarityOrder.length : aIndex;
          bValue = bIndex === -1 ? rarityOrder.length : bIndex;
          break;
        }
        case 'id':
          aValue = a.id;
          bValue = b.id;
          break;
        case 'name':
          aValue = `${a.modifier} ${a.base_name}`.toLowerCase();
          bValue = `${b.modifier} ${b.base_name}`.toLowerCase();
          break;
        default:
          aValue = a.id;
          bValue = b.id;
      }

      if (typeof aValue === 'string' && typeof bValue === 'string') {
        const comparison = aValue.localeCompare(bValue);
        return currentGridSortOptions.direction === 'asc' ? comparison : -comparison;
      } else if (typeof aValue === 'number' && typeof bValue === 'number') {
        const comparison = aValue - bValue;
        return currentGridSortOptions.direction === 'asc' ? comparison : -comparison;
      }

      return 0;
    });

    return sorted;
  };

  const filteredCurrentCards = applyCurrentGridFiltersAndSorting(cards);

  const shareEnabled = Boolean(initData && userData);
  
  // Feature hooks
  const { orientation, orientationKey, resetTiltReference } = useOrientation();
  const { showModal, modalCard, openModal, closeModal, updateModalCard } = useModal();
  // Expand app and lock viewport height
  useEffect(() => {
    // Immediately expand the app to full height
    TelegramUtils.expandApp();

    // Check if already expanded and capture height
    const checkAndSetHeight = () => {
      if (TelegramUtils.isExpanded()) {
        const height = TelegramUtils.getViewportStableHeight();
        if (height) {
          console.log('Captured expanded viewport height:', height);
          setLockedViewportHeight(prev => {
            // Only update if we don't have a height yet, or if new height is larger
            if (!prev || height > prev) {
              return height;
            }
            return prev;
          });
        }
      }
    };

    // Check immediately
    checkAndSetHeight();

    // Also check after a short delay (in case expand is async)
    const timeoutId = setTimeout(checkAndSetHeight, 100);

    // Listen for viewport changes
    const cleanup = TelegramUtils.onViewportChanged((event) => {
      console.log('Viewport changed, isStateStable:', event.isStateStable);
      
      // Only capture height when the viewport is in a stable state and expanded
      if (event.isStateStable && TelegramUtils.isExpanded()) {
        const height = TelegramUtils.getViewportStableHeight();
        if (height) {
          console.log('Captured stable expanded viewport height:', height);
          setLockedViewportHeight(prev => {
            // Only update if we don't have a height yet, or if new height is larger
            if (!prev || height > prev) {
              return height;
            }
            return prev;
          });
        }
      }
    });

    return () => {
      clearTimeout(timeoutId);
      cleanup();
    };
  }, []);

  // Apply locked viewport height to the app container
  useEffect(() => {
    if (lockedViewportHeight) {
      const appContainer = document.querySelector('.app-container') as HTMLElement;
      if (appContainer) {
        appContainer.style.height = `${lockedViewportHeight}px`;
        appContainer.style.minHeight = `${lockedViewportHeight}px`;
        console.log('Applied locked viewport height to app container:', lockedViewportHeight);
      }
    }
  }, [lockedViewportHeight]);

  // Hide trade/navigation buttons when in single card mode
  useEffect(() => {
    if (userData?.singleCardView) {
      TelegramUtils.hideBackButton();
    }
  }, [userData?.singleCardView]);

  const exitTradeView = useCallback(() => {
    setIsTradeGridActive(false);
    setSelectedCardForTrade(null);
    closeModal();
    setView('current');
    setFilterOptions({ owner: '', rarity: '' });
    setSortOptions({ field: 'rarity', direction: 'desc' });
    TelegramUtils.hideBackButton();
  }, [closeModal]);

  const exitTradeViewRef = useRef(exitTradeView);

  useEffect(() => {
    exitTradeViewRef.current = exitTradeView;
  }, [exitTradeView]);
  
  // Memoized callback functions to prevent infinite re-renders
  const handleTradeClick = useCallback(() => {
    // Handle trade button click in current view (only if trading is enabled)
    if (userData?.enableTrade) {
      // Use modal card if open (grid view case), otherwise use current index card (gallery view case)
      const tradeCard = modalCard || cards[currentIndex];
      
      if (!tradeCard) {
        return;
      }

      if (!tradeCard.chat_id) {
        TelegramUtils.showAlert('This card cannot be traded because it is not associated with a chat yet.');
        return;
      }

      // Close modal if it's open before starting trade
      if (modalCard) {
        closeModal();
      }

      setSelectedCardForTrade(tradeCard);
      setIsTradeGridActive(!hasChatScope);
      setView('all');
    }
  }, [cards, currentIndex, modalCard, userData?.enableTrade, hasChatScope, closeModal]);

  const handleSelectClick = useCallback(() => {
    // Handle select button click in modal
    if (selectedCardForTrade && modalCard) {
      // Execute the trade via API
      const executeTrade = async () => {
        try {
          const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com';
          const response = await fetch(`${apiBaseUrl}/trade/${selectedCardForTrade.id}/${modalCard.id}`, {
            method: 'POST',
            headers: {
              'Authorization': `tma ${initData}`
            }
          });

          if (response.ok) {
            // Close the WebApp after successful trade request
            TelegramUtils.closeApp();
          } else {
            const errorData = await response.json();
            TelegramUtils.showAlert(`Trade request failed: ${errorData.detail || 'Unknown error'}`);
          }
        } catch (error) {
          console.error('Trade API error:', error);
          TelegramUtils.showAlert('Trade request failed: Network error');
        }
      };

      executeTrade();
      
      // Reset trading state
      exitTradeView();
    }
  }, [selectedCardForTrade, modalCard, initData, exitTradeView]);

  const handleCurrentTabClick = useCallback(() => {
    exitTradeView();
    // Don't reset grid view state - preserve it
  }, [exitTradeView]);

  const handleAllTabClick = useCallback(() => {
    setIsTradeGridActive(false);
    setSelectedCardForTrade(null);
    setView('all');
    // Don't reset filters - preserve All view state
  }, []);

  const handleGridToggle = useCallback(() => {
    setIsGridView(!isGridView);
    // Don't reset filters - preserve them when switching between grid/gallery
  }, [isGridView]);  const handleFilterChange = useCallback((newFilters: FilterOptions) => {
    setFilterOptions(newFilters);
  }, []);

  const handleSortChange = useCallback((newSort: SortOptions) => {
    setSortOptions(newSort);
  }, []);

  const handleCurrentGridFilterChange = useCallback((newFilters: FilterOptions) => {
    setCurrentGridFilterOptions(newFilters);
  }, []);

  const handleCurrentGridSortChange = useCallback((newSort: SortOptions) => {
    setCurrentGridSortOptions(newSort);
  }, []);

  const handleShareCard = useCallback(async (cardId: number) => {
    if (!initData) {
      TelegramUtils.showAlert('Unable to share card: missing Telegram init data.');
      return;
    }
    if (!userData) {
      TelegramUtils.showAlert('Unable to share card: user data unavailable.');
      return;
    }

    try {
      await ApiService.shareCard(cardId, userData.currentUserId, initData);
      TelegramUtils.showAlert('Shared to chat!');
    } catch (err) {
      console.error('Share card error:', err);
      const message = err instanceof Error ? err.message : 'Failed to share card.';
      TelegramUtils.showAlert(message);
    }
  }, [initData, userData]);

  useEffect(() => {
    if (!isTradeView) {
      TelegramUtils.hideBackButton();
      return;
    }

    const cleanup = TelegramUtils.setupBackButton(() => {
      exitTradeViewRef.current();
    });

    return cleanup;
  }, [isTradeView]);
  
  // Lock button handler
  const handleLockClick = () => {
    if (!userData || !initData) return;

    const targetCard = modalCard || cards[currentIndex];
    if (!targetCard) return;

    if (!targetCard.chat_id) {
      TelegramUtils.showAlert('Unable to lock this card because it is not associated with a chat yet.');
      return;
    }

    void ensureClaimBalance(targetCard.chat_id);

    setShowLockDialog(true);
  };

  // Helper function to update card lock state immutably
  const updateCardLockState = (cardId: number, locked: boolean) => {
    // Update modal card if it matches
    if (modalCard && modalCard.id === cardId) {
      updateModalCard({ locked });
    }
    
    // Note: We don't update the cards array because it comes from useCards hook
    // and is read-only. The card objects are mutable references, so we update them directly.
    // When the modal closes and reopens, or when navigating, the cards will have the updated state.
    const cardInArray = cards.find(c => c.id === cardId);
    if (cardInArray) {
      cardInArray.locked = locked;
    }
  };

  const handleLockConfirm = async () => {
    if (!userData || !initData || lockingCard) return;

    const targetCard = modalCard || cards[currentIndex];
    if (!targetCard) return;

    const chatId = targetCard.chat_id;
    if (!chatId) {
      TelegramUtils.showAlert('Unable to lock this card because it is not associated with a chat yet.');
      return;
    }

    try {
      setLockingCard(true);
      const isCurrentlyLocked = targetCard.locked || false;
      const result = await ApiService.lockCard(
        targetCard.id,
        userData.currentUserId,
        chatId,
        !isCurrentlyLocked,
        initData
      );

      updateCardLockState(targetCard.id, result.locked);

      setChatClaimBalances(prev => ({
        ...prev,
        [chatId]: {
          balance: result.balance,
          loading: false,
          error: undefined
        }
      }));

      TelegramUtils.showAlert(result.message);
    } catch (error) {
      console.error('Failed to lock/unlock card:', error);
      setChatClaimBalances(prev => {
        const existing = prev[chatId];
        const message = error instanceof Error ? error.message : 'Failed to lock/unlock card';
        return {
          ...prev,
          [chatId]: existing
            ? { ...existing, loading: false, error: message }
            : { balance: null, loading: false, error: message }
        };
      });
      TelegramUtils.showAlert(error instanceof Error ? error.message : 'Failed to lock/unlock card');
    } finally {
      setLockingCard(false);
      setShowLockDialog(false);
    }
  };

  const handleLockCancel = () => {
    setShowLockDialog(false);
  };

  // Action Panel logic (replaces useMainButton)
  const getActionButtons = (): ActionButton[] => {
    if (loading || error) {
      return [];
    }

    const buttons: ActionButton[] = [];

    // Show Lock button in current view for own collection when chat_id is available
    if (userData?.isOwnCollection && initData && cards.length > 0 && view === 'current' && !selectedCardForTrade && (!isGridView || modalCard)) {
      const currentCard = modalCard || cards[currentIndex];
      if (currentCard?.chat_id) {
        const isLocked = currentCard.locked || false;
        buttons.push({
          id: 'lock',
          text: isLocked ? 'Unlock' : 'Lock',
          onClick: handleLockClick,
          variant: 'secondary'
        });
      }
    }

    // Show Trade button in current view for own collection (only if trading is enabled)
    // Allow in gallery view always, or in grid view when a modal card is open
    if (userData?.isOwnCollection && userData.enableTrade && cards.length > 0 && view === 'current' && !selectedCardForTrade && (!isGridView || modalCard)) {
      buttons.push({
        id: 'trade',
        text: 'Trade',
        onClick: handleTradeClick,
        variant: 'primary'
      });
    }
    // Show Select button in modal when trading and viewing others' cards (only if trading is enabled)
    else if (userData?.enableTrade && selectedCardForTrade && modalCard && view === 'all' && modalCard.owner && modalCard.owner !== TelegramUtils.getCurrentUsername()) {
      buttons.push({
        id: 'select',
        text: 'Select',
        onClick: handleSelectClick,
        variant: 'primary'
      });
    }

    return buttons;
  };

  const actionButtons = getActionButtons();
  const isActionPanelVisible = actionButtons.length > 0;

  const collectionOwnerLabel = (() => {
    if (!userData) {
      return 'Collection';
    }
    if (userData.collectionDisplayName && userData.collectionDisplayName.trim().length > 0) {
      return userData.collectionDisplayName;
    }
    if (userData.collectionUsername && userData.collectionUsername.trim().length > 0) {
      return `@${userData.collectionUsername}`;
    }
    return 'Collection';
  })();
  
  // Event handlers
  const swipeHandlers = useSwipeHandlers({
    cardsLength: cards.length,
    currentIndex,
    onIndexChange: setCurrentIndex,
    onTiltReset: resetTiltReference
  });

  // Preload slots images when in slots view
  useEffect(() => {
    if (!userData?.slotsView || slotsSymbols.length === 0) {
      setSlotsImagesLoaded(false);
      return;
    }

    const imagesToLoad = slotsSymbols
      .filter(symbol => symbol.iconb64)
      .map(symbol => symbol.iconb64!);

    if (imagesToLoad.length === 0) {
      setSlotsImagesLoaded(true);
      return;
    }

    setSlotsImagesLoaded(false);
    let loadedCount = 0;
    const totalImages = imagesToLoad.length;
    const promises: Promise<void>[] = [];

    imagesToLoad.forEach((iconb64) => {
      const promise = new Promise<void>((resolve) => {
        const img = new Image();
        // Use the same helper that Slots component uses to ensure URLs are cached
        const objectUrl = getIconObjectUrl(iconb64);
        
        const handleLoad = async () => {
          try {
            // Ensure the image is fully decoded before considering it loaded
            await img.decode();
            loadedCount += 1;
            if (loadedCount === totalImages) {
              // Add a small delay to ensure all images are fully painted
              setTimeout(() => {
                setSlotsImagesLoaded(true);
              }, 50);
            }
            resolve();
          } catch {
            loadedCount += 1;
            if (loadedCount === totalImages) {
              setTimeout(() => {
                setSlotsImagesLoaded(true);
              }, 50);
            }
            resolve();
          }
        };

        const handleError = () => {
          loadedCount += 1;
          if (loadedCount === totalImages) {
            setTimeout(() => {
              setSlotsImagesLoaded(true);
            }, 50);
          }
          resolve();
        };

        img.addEventListener('load', handleLoad);
        img.addEventListener('error', handleError);
        img.src = objectUrl;
      });
      
      promises.push(promise);
    });

    // Wait for all images to be loaded and decoded
    Promise.all(promises).catch(() => {
      // If anything fails, still mark as loaded to not block forever
      setSlotsImagesLoaded(true);
    });
  }, [userData?.slotsView, slotsSymbols]);

  // Loading state
  if (loading || (userData?.slotsView && (slotsLoading || slotsSymbols.length === 0 || !slotsImagesLoaded))) {
    return <div className="app-container"><h1>Loading...</h1></div>;
  }

  // Error state
  if (error || (userData?.slotsView && slotsError)) {
    const displayError = error || slotsError;
    return <div className="app-container"><h1>Error: {displayError}</h1></div>;
  }

  // Slots View
  if (userData?.slotsView && userData.chatId && initData) {
    return (
      <div className="app-container">
        <Slots
          symbols={slotsSymbols}
          spins={slotsSpins}
          userId={userData.currentUserId}
          chatId={userData.chatId}
          initData={initData}
          onSpinConsumed={refetchSpins}
        />
      </div>
    );
  }

  // Single Card View (no tabs, no navigation or trade UI)
  if (userData?.singleCardView && userData.singleCardId && initData) {
    return (
      <div className="app-container">
        <SingleCardView
          cardId={userData.singleCardId}
          initData={initData}
          orientation={orientation}
          orientationKey={orientationKey}
        />
      </div>
    );
  }

  return (
    <>
      {showLockDialog && (
        <div 
          className="share-dialog-overlay" 
          onClick={(e) => {
            e.stopPropagation();
            setShowLockDialog(false);
          }}
        >
          <div 
            className="share-dialog"
            onClick={(e) => e.stopPropagation()}
          >
            {(() => {
              // Use modal card if open (grid view), otherwise use current index card
              const currentCard = modalCard || cards[currentIndex];
              const isLocked = currentCard?.locked || false;
              const claimState = currentCard?.chat_id ? chatClaimBalances[currentCard.chat_id] : undefined;

              if (!currentCard) {
                return <p>No card selected.</p>;
              }

              const renderBalance = () => {
                if (!claimState) {
                  return null;
                }

                if (claimState.loading) {
                  return (
                    <p className="lock-dialog-balance">
                      Balance: <em>Loading...</em>
                    </p>
                  );
                }

                if (claimState.error) {
                  return (
                    <p className="lock-dialog-balance">
                      Balance unavailable
                    </p>
                  );
                }

                if (claimState.balance !== null) {
                  return (
                    <p className="lock-dialog-balance">
                      Balance: <strong>{claimState.balance}</strong>
                    </p>
                  );
                }

                return null;
              };
              
              if (isLocked) {
                return (
                  <>
                    <p>Unlock <strong>{currentCard?.modifier} {currentCard?.base_name}</strong>?</p>
                    <p className="lock-dialog-subtitle">Claim point will <strong>not</strong> be refunded.</p>
                    {renderBalance()}
                  </>
                );
              } else {
                return (
                  <>
                    <p>Lock <strong>{currentCard?.modifier} {currentCard?.base_name}</strong>?</p>
                    <p className="lock-dialog-subtitle">This will consume <strong>1 claim point</strong></p>
                    {renderBalance()}
                  </>
                );
              }
            })()}
            <div className="share-dialog-buttons">
              <button 
                onClick={handleLockConfirm} 
                className="share-confirm-btn"
                disabled={lockingCard}
              >
                {lockingCard ? 'Processing...' : 'Yes'}
              </button>
              <button 
                onClick={handleLockCancel} 
                className="share-cancel-btn"
                disabled={lockingCard}
              >
                No
              </button>
            </div>
          </div>
        </div>
      )}
      <div className={`app-container ${isActionPanelVisible ? 'with-action-panel' : ''}`} {...(view === 'current' ? swipeHandlers : {})}>
      {/* Tab Navigation */}
      <div className="tabs">
        <button 
          className={`tab ${view === 'current' ? 'active' : ''}`} 
          onClick={handleCurrentTabClick}
        >
          Current
        </button>
        {hasChatScope && (
          <button 
            className={`tab ${view === 'all' && !isTradeGridActive ? 'active' : ''}`} 
            onClick={handleAllTabClick}
          >
            All
          </button>
        )}
      </div>

      <div className="app-content">
        <div className="title-container">
          {view === 'current' && cards.length > 0 && !isGridView && (
            <div className="card-position-indicator">
              <span className="position-current">{currentIndex + 1}</span>
              <span className="position-separator"> / </span>
              <span className="position-total">{cards.length}</span>
            </div>
          )}
          {view === 'current' && cards.length > 0 && (
            <button 
              className="view-toggle-button"
              onClick={handleGridToggle}
              onTouchStart={(e) => e.stopPropagation()}
              onTouchEnd={(e) => e.stopPropagation()}
              aria-label={isGridView ? "Currently in grid view" : "Currently in gallery view"}
            >
              {isGridView ? "Grid" : "Gallery"}
            </button>
          )}
          <h1 className="app-title">
            {view === 'all'
              ? isTradeView && tradeCardName
                ? `Trade for ${tradeCardName}`
                : 'All cards'
              : `${collectionOwnerLabel}'s collection`}
          </h1>
        </div>
        
        {/* Current View */}
        {view === 'current' && (
          <>
            {cards.length > 0 ? (
              <>
                {isGridView ? (
                  <>
                    <FilterSortControls
                      cards={cards}
                      filterOptions={currentGridFilterOptions}
                      sortOptions={currentGridSortOptions}
                      onFilterChange={handleCurrentGridFilterChange}
                      onSortChange={handleCurrentGridSortChange}
                      showOwnerFilter={false}
                    />
                    {filteredCurrentCards.length === 0 ? (
                      <div className="no-cards-container">
                        <h2>No cards match your filter</h2>
                        <p>Try selecting a different rarity or clearing the filter.</p>
                      </div>
                    ) : (
                      <AllCards
                        cards={filteredCurrentCards}
                        onCardClick={openModal}
                        initData={initData}
                      />
                    )}
                  </>
                ) : (
                  <div className={`card-container ${isActionPanelVisible ? 'with-action-panel' : ''}`}>
                    {/* Current Card */}
                    <Card 
                      {...cards[currentIndex]} 
                      orientation={orientation}
                      tiltKey={orientationKey}
                      initData={initData}
                      shiny={true}
                      onShare={shareEnabled ? handleShareCard : undefined}
                      showShareButton={shareEnabled}
                      onCardOpen={handleCardOpen}
                    />
                  </div>
                )}
              </>
            ) : (
              <p>
                {userData?.isOwnCollection
                  ? "You don't own any cards yet."
                  : `${collectionOwnerLabel} doesn't own any cards yet.`}
              </p>
            )}
          </>
        )}

        {/* All Cards View */}
        {view === 'all' && (
          <>
            {allCardsLoading ? (
              <div className="loading-container">
                <h2>{isTradeView ? 'Loading trade options...' : 'Loading all cards...'}</h2>
              </div>
            ) : allCardsError ? (
              <div className="error-container">
                <h2>{isTradeView ? 'Error loading trade options' : 'Error loading cards'}</h2>
                <p>{allCardsError}</p>
                <button onClick={refetchAllCards}>Retry</button>
              </div>
            ) : baseDisplayedCards.length === 0 ? (
              <div className="no-cards-container">
                <h2>{isTradeView ? 'No trade options' : 'No cards found'}</h2>
                <p>
                  {isTradeView
                    ? 'No other cards are available in this chat right now.'
                    : 'There are no cards in the system yet.'}
                </p>
              </div>
            ) : (
              <>
                <FilterSortControls
                  cards={baseDisplayedCards}
                  filterOptions={filterOptions}
                  sortOptions={sortOptions}
                  onFilterChange={handleFilterChange}
                  onSortChange={handleSortChange}
                />
                {displayedCards.length === 0 ? (
                  <div className="no-cards-container">
                    <h2>No cards match your filters</h2>
                    <p>Try adjusting your filter settings to see more cards.</p>
                  </div>
                ) : (
                  <AllCards
                    cards={displayedCards}
                    onCardClick={openModal}
                    initData={initData}
                  />
                )}
              </>
            )}
          </>
        )}
      </div>

      {/* Card Modal */}
      {modalCard && (
        <CardModal
          isOpen={showModal}
          card={modalCard}
          orientation={orientation}
          orientationKey={orientationKey}
          initData={initData}
          onClose={closeModal}
          onShare={shareEnabled ? handleShareCard : undefined}
          onCardOpen={handleCardOpen}
        />
      )}

      {/* Action Panel */}
      <ActionPanel
        buttons={actionButtons}
        visible={isActionPanelVisible}
      />
      </div>
    </>
  );
};

export default App;
