import { useState, useCallback, useEffect, useRef } from 'react';
import './App.css';

// Components
import SingleCardView from './components/SingleCardView';
import CardModal from './components/CardModal';
import ActionPanel from './components/ActionPanel';
import BurnConfirmDialog from './components/BurnConfirmDialog';
import CardView from './components/CardView';
import LockConfirmDialog from './components/LockConfirmDialog';
import Casino from './components/Casino';
import AppLoading from './components/AppLoading';
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
import { RARITY_SEQUENCE } from './utils/rarityStyles';

// Services
import { ApiService } from './services/api';

// Types
import type { CardData, ClaimBalanceState, View, ProfileState, UserProfile } from './types';

// Build info
import { BUILD_INFO } from './build-info';

function App() {
  // Log build info to console for debugging (only once on mount)
  useEffect(() => {
    console.log('App build info:', BUILD_INFO);
  }, []);
  
  // Viewport height management - lock in the maximum height
  const [lockedViewportHeight, setLockedViewportHeight] = useState<number | null>(null);
  
  // Core data hooks
  const {
    cards,
    loading,
    error,
    userData,
    initData,
    refetch: refetchCards,
    updateCard: updateCardInCollection
  } = useCards();
  const { symbols: slotsSymbols, spins: slotsSpins, megaspin: slotsMegaspin, loading: slotsLoading, error: slotsError, refetchSpins, updateSpins, updateMegaspin } = useSlots(
    userData?.casinoView && userData.chatId ? userData.chatId : undefined,
    userData?.currentUserId
  );
  
  // Only enable orientation tracking when not in casino view (for card tilt effects)
  const { orientation, orientationKey, resetTiltReference } = useOrientation({
    enabled: !userData?.casinoView
  });
  
  // UI state
  const [currentIndex, setCurrentIndex] = useState(0);
  const [view, setView] = useState<View>('current');
  const [selectedCardForTrade, setSelectedCardForTrade] = useState<CardData | null>(null);
  const [isTradeGridActive, setIsTradeGridActive] = useState(false);
  const [isGridView, setIsGridView] = useState(false);
  const [showBurnDialog, setShowBurnDialog] = useState(false);
  const [showLockDialog, setShowLockDialog] = useState(false);
  const [lockingCard, setLockingCard] = useState(false);
  const [burningCard, setBurningCard] = useState(false);
  const [triggerBurn, setTriggerBurn] = useState(false);
  const [isBurningInProgress, setIsBurningInProgress] = useState(false);
  const [chatProfiles, setChatProfiles] = useState<Record<string, ProfileState>>({});
  const [viewedProfile, setViewedProfile] = useState<ProfileState>({ profile: null, loading: false });
  const profileRequestsRef = useRef<Map<string, Promise<UserProfile | null>>>(new Map());
  const pendingChatIdsRef = useRef<Set<string>>(new Set());
  const cardConfigLoadedRef = useRef(false);
  const [burnRewards, setBurnRewards] = useState<Record<string, number> | null>(null);
  const [lockCosts, setLockCosts] = useState<Record<string, number> | null>(null);
  const burnResultRef = useRef<{
    rarity: string;
    cardName: string;
    spinsAwarded: number;
    newSpinTotal: number;
    cardId: number;
    burnedCardIndex: number;
  } | null>(null);

  // Filter and sort state
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    owner: '',
    rarity: '',
    locked: '',
    characterName: '',
    setName: ''
  });
  const [sortOptions, setSortOptions] = useState<SortOptions>({
    field: 'rarity',
    direction: 'desc'
  });
  
  // Current view grid filter and sort state (only rarity filter, but full sort options)
  const [currentGridFilterOptions, setCurrentGridFilterOptions] = useState<FilterOptions>({
    owner: '', // Always empty for current view
    rarity: '',
    locked: '',
    characterName: '',
    setName: ''
  });
  const [currentGridSortOptions, setCurrentGridSortOptions] = useState<SortOptions>({
    field: 'rarity',
    direction: 'desc'
  });

  const hasChatScope = Boolean(userData?.chatId);
  const isTradeMode = Boolean(selectedCardForTrade);
  const isTradeView = view === 'all' && isTradeMode;
  const activeTradeCardId = isTradeMode && selectedCardForTrade ? selectedCardForTrade.id : null;
  const cardsScopeChatId = isTradeMode && selectedCardForTrade?.chat_id
    ? selectedCardForTrade.chat_id
    : userData?.chatId ?? null;
  const shouldFetchAllCards = !userData?.casinoView && (hasChatScope || activeTradeCardId !== null);

  const ensureUserProfile = useCallback(async (
    chatId: string,
    options: { force?: boolean } = {}
  ): Promise<UserProfile | null> => {
    if (!chatId) {
      return null;
    }

    if (!userData || !initData) {
      pendingChatIdsRef.current.add(chatId);
      return null;
    }

    pendingChatIdsRef.current.delete(chatId);

    const existingState = chatProfiles[chatId];
    const fallbackProfile = existingState?.profile ?? null;

    if (!options.force && existingState && fallbackProfile !== null && !existingState.error) {
      return fallbackProfile;
    }

    if (!options.force && profileRequestsRef.current.has(chatId)) {
      return profileRequestsRef.current.get(chatId)!;
    }

    const fetchPromise = (async () => {
      setChatProfiles(prev => ({
        ...prev,
        [chatId]: {
          profile: prev[chatId]?.profile ?? null,
          loading: true,
          error: undefined
        }
      }));
      try {
        const result = await ApiService.fetchUserProfile(userData.currentUserId, chatId, initData);
        setChatProfiles(prev => ({
          ...prev,
          [chatId]: {
            profile: result,
            loading: false,
            error: undefined
          }
        }));
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to fetch user profile';
        console.error(`Failed to fetch user profile for chat ${chatId}`, err);
        setChatProfiles(prev => ({
          ...prev,
          [chatId]: {
            profile: prev[chatId]?.profile ?? fallbackProfile,
            loading: false,
            error: message
          }
        }));
        return fallbackProfile;
      }
    })();

    profileRequestsRef.current.set(chatId, fetchPromise);

    const resolvedProfile = await fetchPromise;
    profileRequestsRef.current.delete(chatId);

    return resolvedProfile;
  }, [chatProfiles, initData, userData]);

  const handleCardOpen = useCallback((card: Pick<CardData, 'id' | 'chat_id'>) => {
    if (!card.chat_id) {
      return;
    }

    void ensureUserProfile(card.chat_id);
  }, [ensureUserProfile]);

  useEffect(() => {
    if (!userData || !initData || pendingChatIdsRef.current.size === 0) {
      return;
    }

    const queuedChatIds = Array.from(pendingChatIdsRef.current);
    pendingChatIdsRef.current.clear();

    queuedChatIds.forEach(chatId => {
      void ensureUserProfile(chatId, { force: true });
    });
  }, [ensureUserProfile, initData, userData]);

  useEffect(() => {
    if (!userData || !initData || !userData.chatId) return;

    const fetchViewedProfile = async () => {
      setViewedProfile(prev => ({ ...prev, loading: true, error: undefined }));
      try {
        const userId = userData.isOwnCollection ? userData.currentUserId : userData.targetUserId;
        const result = await ApiService.fetchUserProfile(userId, userData.chatId!, initData);
        setViewedProfile({ profile: result, loading: false, error: undefined });
      } catch (err) {
        setViewedProfile({ profile: null, loading: false, error: err instanceof Error ? err.message : 'Failed' });
      }
    };

    fetchViewedProfile();
  }, [userData, initData]);

  // Load card config when card view is first loaded
  useEffect(() => {
    if (!initData || !userData || userData.casinoView || userData.singleCardView) {
      return;
    }

    if (cardConfigLoadedRef.current) {
      return;
    }

    cardConfigLoadedRef.current = true;

    const loadCardConfig = async () => {
      try {
        const config = await ApiService.fetchCardConfig(initData);
        setBurnRewards(config.burn_rewards);
        setLockCosts(config.lock_costs);
        console.log('Card config loaded:', config);
      } catch (err) {
        console.error('Failed to fetch card config:', err);
        // Non-critical error, continue without card config
        cardConfigLoadedRef.current = false;
      }
    };

    void loadCardConfig();
  }, [initData, userData]);

  const {
    allCards,
    loading: allCardsLoading,
    error: allCardsError,
    refetch: refetchAllCards,
    updateCard: updateAllCardsCollection
  } = useAllCards(initData, cardsScopeChatId, {
    enabled: shouldFetchAllCards,
    tradeCardId: activeTradeCardId
  });

  const refreshCardsData = useCallback(async () => {
    await refetchCards();
    if (shouldFetchAllCards) {
      await refetchAllCards();
    }
  }, [refetchCards, refetchAllCards, shouldFetchAllCards]);

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

    if (filterOptions.locked) {
      const shouldBeLocked = filterOptions.locked === 'locked';
      filtered = filtered.filter(card => Boolean(card.locked) === shouldBeLocked);
    }

    // Apply character name filter
    if (filterOptions.characterName) {
      filtered = filtered.filter(card => card.base_name === filterOptions.characterName);
    }

    // Apply set name filter
    if (filterOptions.setName) {
      filtered = filtered.filter(card => card.set_name === filterOptions.setName);
    }

    // Apply sorting
    const sorted = [...filtered].sort((a, b) => {
      let aValue: string | number;
      let bValue: string | number;

      switch (sortOptions.field) {
        case 'rarity': {
          // Use centralized rarity sequence: Common -> Rare -> Epic -> Legendary -> Unique
          const rarityArray = [...RARITY_SEQUENCE] as string[];
          const aIndex = rarityArray.indexOf(a.rarity);
          const bIndex = rarityArray.indexOf(b.rarity);
          // If rarity not found in order, put it at the end
          aValue = aIndex === -1 ? rarityArray.length : aIndex;
          bValue = bIndex === -1 ? rarityArray.length : bIndex;
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

  const baseDisplayedCards = isTradeMode && selectedCardForTrade
    ? allCards.filter((card) =>
        card.id !== selectedCardForTrade.id &&
        (userData?.currentUserId == null || card.user_id !== userData.currentUserId)
      )
    : allCards;

  const displayedCards = applyFiltersAndSorting(baseDisplayedCards);

  // Apply filtering and sorting for current view grid
  const applyCurrentGridFiltersAndSorting = (cards: CardData[]) => {
    let filtered = cards;

    // Apply rarity filter
    if (currentGridFilterOptions.rarity) {
      filtered = filtered.filter(card => card.rarity === currentGridFilterOptions.rarity);
    }

    if (currentGridFilterOptions.locked) {
      const shouldBeLocked = currentGridFilterOptions.locked === 'locked';
      filtered = filtered.filter(card => Boolean(card.locked) === shouldBeLocked);
    }

    // Apply character name filter
    if (currentGridFilterOptions.characterName) {
      filtered = filtered.filter(card => card.base_name === currentGridFilterOptions.characterName);
    }

    // Apply set name filter
    if (currentGridFilterOptions.setName) {
      filtered = filtered.filter(card => card.set_name === currentGridFilterOptions.setName);
    }

    // Apply sorting
    const sorted = [...filtered].sort((a, b) => {
      let aValue: string | number;
      let bValue: string | number;

      switch (currentGridSortOptions.field) {
        case 'rarity': {
          // Use centralized rarity sequence: Common -> Rare -> Epic -> Legendary -> Unique
          const rarityArray = [...RARITY_SEQUENCE] as string[];
          const aIndex = rarityArray.indexOf(a.rarity);
          const bIndex = rarityArray.indexOf(b.rarity);
          // If rarity not found in order, put it at the end
          aValue = aIndex === -1 ? rarityArray.length : aIndex;
          bValue = bIndex === -1 ? rarityArray.length : bIndex;
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
  const { showModal, modalCard, openModal, closeModal, updateModalCard } = useModal();
  const currentDialogCard = modalCard ?? cards[currentIndex] ?? null;
  const currentDialogProfileState = currentDialogCard?.chat_id
    ? chatProfiles[currentDialogCard.chat_id]
    : undefined;

  const currentDialogClaimState: ClaimBalanceState | undefined = currentDialogProfileState
    ? {
        balance: currentDialogProfileState.profile?.claim_balance ?? null,
        loading: currentDialogProfileState.loading,
        error: currentDialogProfileState.error
      }
    : undefined;
  const currentDialogCardName = currentDialogCard
    ? `${currentDialogCard.modifier} ${currentDialogCard.base_name}`.trim()
    : null;
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

  const switchToCurrentView = useCallback((options?: { preserveAllFilters?: boolean }) => {
    setIsTradeGridActive(false);
    setSelectedCardForTrade(null);
    closeModal();
    setView('current');
    if (!options?.preserveAllFilters) {
      setFilterOptions({ owner: '', rarity: '', locked: '', characterName: '', setName: '' });
      setSortOptions({ field: 'rarity', direction: 'desc' });
    }
    TelegramUtils.hideBackButton();
  }, [closeModal]);

  const switchToCurrentViewRef = useRef(switchToCurrentView);

  useEffect(() => {
    switchToCurrentViewRef.current = switchToCurrentView;
  }, [switchToCurrentView]);
  
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
      switchToCurrentView();
    }
  }, [selectedCardForTrade, modalCard, initData, switchToCurrentView]);

  const handleCurrentTabClick = useCallback(() => {
    const preserveAllFilters = !isTradeMode;
    switchToCurrentView({ preserveAllFilters });
    // Don't reset grid view state - preserve it
  }, [isTradeMode, switchToCurrentView]);

  const handleAllTabClick = useCallback(() => {
    setIsTradeGridActive(false);
    setSelectedCardForTrade(null);
    setView('all');
    // Don't reset filters - preserve All view state
  }, []);

  const handleProfileTabClick = useCallback(() => {
    setIsTradeGridActive(false);
    setSelectedCardForTrade(null);
    setView('profile');
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
      switchToCurrentViewRef.current();
    });

    return cleanup;
  }, [isTradeView]);
  
  const handleBurnClick = () => {
    if (!userData || !initData) return;

    const targetCard = modalCard || cards[currentIndex];
    if (!targetCard) return;

    if (!targetCard.chat_id) {
      TelegramUtils.showAlert('Unable to burn this card because it is not associated with a chat yet.');
      return;
    }

    setShowBurnDialog(true);
  };

  const handleBurnConfirm = async () => {
    if (!userData || !initData || burningCard) return;

    const targetCard = modalCard || cards[currentIndex];
    if (!targetCard) return;

    const chatId = targetCard.chat_id;
    if (!chatId) {
      TelegramUtils.showAlert('Unable to burn this card because it is not associated with a chat yet.');
      return;
    }

    try {
      setBurningCard(true);
      
      // Call burn API
      const result = await ApiService.burnCard(
        targetCard.id,
        userData.currentUserId,
        chatId,
        initData
      );

      // Store the result for later use
      const cardName = `${targetCard.modifier} ${targetCard.base_name}`.trim();
      const burnResult = {
        rarity: targetCard.rarity,
        cardName,
        spinsAwarded: result.spins_awarded,
        newSpinTotal: result.new_spin_total,
        cardId: targetCard.id,
        burnedCardIndex: cards.findIndex(c => c.id === targetCard.id),
      };

      // Store in ref for onBurnComplete to access
      burnResultRef.current = burnResult;

      // Close the dialog and trigger burn animation
      setShowBurnDialog(false);
      setTriggerBurn(true);
      setIsBurningInProgress(true);

    } catch (error) {
      console.error('Failed to burn card:', error);
      setShowBurnDialog(false);
      setBurningCard(false);
      TelegramUtils.showAlert(error instanceof Error ? error.message : 'Failed to burn card');
    }
  };

  const handleBurnComplete = async () => {
    // Reset the animation trigger
    setTriggerBurn(false);
    setBurningCard(false);
    setIsBurningInProgress(false);

    // Get the stored burn result
    const burnResult = burnResultRef.current;
    if (!burnResult) return;

    burnResultRef.current = null;

    // Close modal if open
    if (modalCard) {
      closeModal();
    } else if (burnResult.burnedCardIndex !== -1) {
      // In gallery view, adjust current index
      if (cards.length > 1) {
        // If we're at the last card, go to the previous one
        if (burnResult.burnedCardIndex === cards.length - 1) {
          setCurrentIndex(Math.max(0, burnResult.burnedCardIndex - 1));
        }
        // Otherwise stay at the same index (which will now point to the next card)
      } else {
        // Last card burned, reset to 0
        setCurrentIndex(0);
      }
    }

    // Show success notification
    const notification = `${burnResult.rarity} ${burnResult.cardName} burned!\n\nReceived ${burnResult.spinsAwarded} spins\n\nBalance: ${burnResult.newSpinTotal}`;
    TelegramUtils.showAlert(notification);

    // Refetch cards from server to get updated list
    await refreshCardsData();
  };

  const handleBurnCancel = () => {
    setShowBurnDialog(false);
  };

  // Lock button handler
  const handleLockClick = () => {
    if (!userData || !initData) return;

    const targetCard = modalCard || cards[currentIndex];
    if (!targetCard) return;

    if (!targetCard.chat_id) {
      TelegramUtils.showAlert('Unable to lock this card because it is not associated with a chat yet.');
      return;
    }

    const rarityLockCost = Math.max(1, lockCosts?.[targetCard.rarity] ?? 1);
    if (rarityLockCost > 0) {
      void ensureUserProfile(targetCard.chat_id);
    }

    setShowLockDialog(true);
  };

  // Helper function to update card lock state
  const updateCardLockState = (cardId: number, locked: boolean) => {
    // Update modal card if it matches
    if (modalCard && modalCard.id === cardId) {
      updateModalCard({ locked });
    }
    updateCardInCollection(cardId, { locked });
    updateAllCardsCollection(cardId, { locked });
    if (selectedCardForTrade?.id === cardId) {
      setSelectedCardForTrade((previous) =>
        previous
          ? {
              ...previous,
              locked,
            }
          : previous
      );
    }
    // The cards array is updated optimistically for immediate UI feedback (and refetched after API calls)
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

      setChatProfiles(prev => {
        const currentProfile = prev[chatId]?.profile;
        if (!currentProfile) return prev;
        
        return {
          ...prev,
          [chatId]: {
            ...prev[chatId],
            profile: {
              ...currentProfile,
              claim_balance: result.balance
            }
          }
        };
      });

      setLockingCard(false);
      setShowLockDialog(false);
      updateCardLockState(targetCard.id, result.locked);

      if (result.lock_cost !== undefined) {
        setLockCosts(prev => ({
          ...(prev ?? {}),
          [targetCard.rarity]: result.lock_cost,
        }));
      }

      TelegramUtils.showAlert(result.message);

      await refreshCardsData();
    } catch (error) {
      console.error('Failed to lock/unlock card:', error);
      setChatProfiles(prev => {
        const existing = prev[chatId];
        const message = error instanceof Error ? error.message : 'Failed to lock/unlock card';
        return {
          ...prev,
          [chatId]: existing
            ? { ...existing, loading: false, error: message }
            : { profile: null, loading: false, error: message }
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
    const shouldDisableActions = burningCard || isBurningInProgress;

    // Show Lock button in current view for own collection when chat_id is available
    if (userData?.isOwnCollection && initData && cards.length > 0 && view === 'current' && !selectedCardForTrade && (!isGridView || modalCard)) {
      const currentCard = modalCard || cards[currentIndex];
      if (currentCard?.chat_id) {
        const isLocked = currentCard.locked || false;
        buttons.push({
          id: 'burn',
          text: 'Burn',
          onClick: handleBurnClick,
          variant: 'burn-red',
          disabled: shouldDisableActions
        });
        buttons.push({
          id: 'lock',
          text: isLocked ? 'Unlock' : 'Lock',
          onClick: handleLockClick,
          variant: 'lock-grey',
          disabled: shouldDisableActions || lockingCard
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
        variant: 'primary',
        disabled: shouldDisableActions
      });
    }
    // Show Select button in modal when trading and viewing others' cards (only if trading is enabled)
    else if (userData?.enableTrade && selectedCardForTrade && modalCard && view === 'all' && modalCard.owner && modalCard.owner !== TelegramUtils.getCurrentUsername()) {
      buttons.push({
        id: 'select',
        text: 'Select',
        onClick: handleSelectClick,
        variant: 'primary',
        disabled: shouldDisableActions
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

  // Loading state
  if (loading || (userData?.casinoView && (slotsLoading || slotsSymbols.length === 0))) {
    return (
      <div className="app-container">
        <AppLoading title="🎰 Casino" spinsCount={slotsSpins.count} />
      </div>
    );
  }

  // Error state
  if (error || (userData?.casinoView && slotsError)) {
    const displayError = error || slotsError;
    return <div className="app-container"><h1>Error: {displayError}</h1></div>;
  }

  // Casino View
  if (userData?.casinoView && userData.chatId && initData) {
    return (
      <div className="app-container">
        <Casino
          userId={userData.currentUserId}
          chatId={userData.chatId}
          initData={initData}
          slotsSymbols={slotsSymbols}
          slotsSpins={slotsSpins}
          slotsMegaspin={slotsMegaspin}
          refetchSpins={refetchSpins}
          updateSpins={updateSpins}
          updateMegaspin={updateMegaspin}
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

  const currentDialogSpinReward = currentDialogCard && burnRewards
    ? burnRewards[currentDialogCard.rarity] ?? null
    : null;
  const currentDialogLockCost = currentDialogCard
  ? Math.max(1, lockCosts?.[currentDialogCard.rarity] ?? 1)
  : 1;

  return (
    <>
      <BurnConfirmDialog
        isOpen={showBurnDialog}
        onConfirm={handleBurnConfirm}
        onCancel={handleBurnCancel}
        cardName={currentDialogCardName}
        spinReward={currentDialogSpinReward}
        processing={burningCard}
      />
      <LockConfirmDialog
        isOpen={showLockDialog}
        locking={lockingCard}
        card={currentDialogCard}
        lockCost={currentDialogLockCost}
        claimState={currentDialogClaimState}
        onConfirm={handleLockConfirm}
        onCancel={handleLockCancel}
      />
      <div className={`app-container ${isActionPanelVisible ? 'with-action-panel' : ''}`} {...(view === 'current' && !isBurningInProgress ? swipeHandlers : {})}>
        <CardView
          view={view}
          hasChatScope={hasChatScope}
          isTradeGridActive={isTradeGridActive}
          isTradeView={isTradeView}
          tradeCardName={tradeCardName}
          collectionOwnerLabel={collectionOwnerLabel}
          currentIndex={currentIndex}
          tabs={{
            onCurrentTabClick: handleCurrentTabClick,
            onAllTabClick: handleAllTabClick,
            onProfileTabClick: handleProfileTabClick
          }}
          profileView={viewedProfile}
          currentView={{
            cards,
            filteredCards: filteredCurrentCards,
            isGridView,
            isActionPanelVisible,
            shareEnabled,
            orientation,
            orientationKey,
            initData,
            onGridToggle: handleGridToggle,
            onCardOpen: handleCardOpen,
            onOpenModal: openModal,
            onShare: shareEnabled ? handleShareCard : undefined,
            currentGridFilterOptions,
            currentGridSortOptions,
            onCurrentGridFilterChange: handleCurrentGridFilterChange,
            onCurrentGridSortChange: handleCurrentGridSortChange,
            collectionOwnerLabel,
            isOwnCollection: Boolean(userData?.isOwnCollection),
            triggerBurn,
            onBurnComplete: handleBurnComplete,
            isBurning: isBurningInProgress
          }}
          allView={{
            baseCards: baseDisplayedCards,
            displayedCards,
            loading: allCardsLoading,
            error: allCardsError ?? null,
            onRetry: refetchAllCards,
            filterOptions,
            sortOptions,
            onFilterChange: handleFilterChange,
            onSortChange: handleSortChange,
            initData,
            onOpenModal: openModal
          }}
        />

      {/* Card Modal */}
      {modalCard && (
        <CardModal
          isOpen={showModal}
          card={modalCard}
          orientation={orientation}
          orientationKey={orientationKey}
          initData={initData}
          onClose={isBurningInProgress ? () => {} : closeModal}
          onShare={shareEnabled ? handleShareCard : undefined}
          onCardOpen={handleCardOpen}
          triggerBurn={triggerBurn}
          onBurnComplete={handleBurnComplete}
          isBurning={isBurningInProgress}
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
