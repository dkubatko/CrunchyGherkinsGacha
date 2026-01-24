import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import '@/App.css';

// Components
import { CardModal, CollectionLayout } from '@/components/cards';
import { ActionPanel, Title } from '@/components/common';
import { BurnConfirmDialog, LockConfirmDialog } from '@/components/dialogs';
import type { FilterOptions, SortOptions } from '@/components/cards';
import type { ActionButton } from '@/components/common';

// Hooks
import {
  useAllCards,
  useOrientation,
  useModal,
  useSwipeHandlers,
  useCollectionCards,
} from '@/hooks';

// Utils
import { TelegramUtils } from '@/utils/telegram';
import { RARITY_SEQUENCE } from '@/utils/rarityStyles';

// Services
import { ApiService } from '@/services/api';

// Types
import type { CardData, ClaimBalanceState, View, ProfileState, UserProfile } from '@/types';

interface CollectionPageProps {
  currentUserId: number;
  targetUserId: number;
  chatId: string | null;
  isOwnCollection: boolean;
  enableTrade: boolean;
  initData: string;
}

export const CollectionPage = ({
  currentUserId,
  targetUserId: initialTargetUserId,
  chatId,
  isOwnCollection: initialIsOwnCollection,
  enableTrade: initialEnableTrade,
  initData
}: CollectionPageProps) => {
  // Core data hooks
  const {
    cards,
    loading,
    error,
    targetUserId,
    isOwnCollection,
    enableTrade,
    collectionDisplayName,
    collectionUsername,
    refetch: refetchCards,
    updateCard: updateCardInCollection
  } = useCollectionCards(initialTargetUserId, chatId, initData, {
    initialIsOwnCollection,
    initialEnableTrade,
    currentUserId
  });

  // Only enable orientation tracking for card tilt effects
  const { orientation, orientationKey, resetTiltReference } = useOrientation({ enabled: true });
  
  // UI state
  const [currentIndex, setCurrentIndex] = useState(0);
  const [view, setView] = useState<View>('current');
  const [selectedCardForTrade, setSelectedCardForTrade] = useState<CardData | null>(null);
  const [isTradeGridActive, setIsTradeGridActive] = useState(false);
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
  
  // Current view grid filter and sort state
  const [currentGridFilterOptions, setCurrentGridFilterOptions] = useState<FilterOptions>({
    owner: '',
    rarity: '',
    locked: '',
    characterName: '',
    setName: ''
  });
  const [currentGridSortOptions, setCurrentGridSortOptions] = useState<SortOptions>({
    field: 'rarity',
    direction: 'desc'
  });

  const hasChatScope = Boolean(chatId);
  const isTradeMode = Boolean(selectedCardForTrade);
  const isTradeView = view === 'all' && isTradeMode;
  const activeTradeCardId = isTradeMode && selectedCardForTrade ? selectedCardForTrade.id : null;
  const cardsScopeChatId = isTradeMode && selectedCardForTrade?.chat_id
    ? selectedCardForTrade.chat_id
    : chatId;
  const shouldFetchAllCards = hasChatScope || activeTradeCardId !== null;

  const ensureUserProfile = useCallback(async (
    profileChatId: string,
    options: { force?: boolean } = {}
  ): Promise<UserProfile | null> => {
    if (!profileChatId) {
      return null;
    }

    pendingChatIdsRef.current.delete(profileChatId);

    const existingState = chatProfiles[profileChatId];
    const fallbackProfile = existingState?.profile ?? null;

    if (!options.force && existingState && fallbackProfile !== null && !existingState.error) {
      return fallbackProfile;
    }

    if (!options.force && profileRequestsRef.current.has(profileChatId)) {
      return profileRequestsRef.current.get(profileChatId)!;
    }

    const fetchPromise = (async () => {
      setChatProfiles(prev => ({
        ...prev,
        [profileChatId]: {
          profile: prev[profileChatId]?.profile ?? null,
          loading: true,
          error: undefined
        }
      }));
      try {
        const result = await ApiService.fetchUserProfile(currentUserId, profileChatId, initData);
        setChatProfiles(prev => ({
          ...prev,
          [profileChatId]: {
            profile: result,
            loading: false,
            error: undefined
          }
        }));
        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to fetch user profile';
        console.error(`Failed to fetch user profile for chat ${profileChatId}`, err);
        setChatProfiles(prev => ({
          ...prev,
          [profileChatId]: {
            profile: prev[profileChatId]?.profile ?? fallbackProfile,
            loading: false,
            error: message
          }
        }));
        return fallbackProfile;
      }
    })();

    profileRequestsRef.current.set(profileChatId, fetchPromise);

    const resolvedProfile = await fetchPromise;
    profileRequestsRef.current.delete(profileChatId);

    return resolvedProfile;
  }, [chatProfiles, initData, currentUserId]);

  const handleCardOpen = useCallback((card: Pick<CardData, 'id' | 'chat_id'>) => {
    if (!card.chat_id) {
      return;
    }
    void ensureUserProfile(card.chat_id);
  }, [ensureUserProfile]);

  useEffect(() => {
    if (pendingChatIdsRef.current.size === 0) {
      return;
    }

    const queuedChatIds = Array.from(pendingChatIdsRef.current);
    pendingChatIdsRef.current.clear();

    queuedChatIds.forEach(queuedChatId => {
      void ensureUserProfile(queuedChatId, { force: true });
    });
  }, [ensureUserProfile]);

  useEffect(() => {
    if (!chatId) return;

    const fetchViewedProfile = async () => {
      setViewedProfile(prev => ({ ...prev, loading: true, error: undefined }));
      try {
        const userId = isOwnCollection ? currentUserId : targetUserId;
        const result = await ApiService.fetchUserProfile(userId, chatId, initData);
        setViewedProfile({ profile: result, loading: false, error: undefined });
      } catch (err) {
        setViewedProfile({ profile: null, loading: false, error: err instanceof Error ? err.message : 'Failed' });
      }
    };

    fetchViewedProfile();
  }, [currentUserId, targetUserId, isOwnCollection, chatId, initData]);

  // Load card config when card view is first loaded
  useEffect(() => {
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
        cardConfigLoadedRef.current = false;
      }
    };

    void loadCardConfig();
  }, [initData]);

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
  const applyFiltersAndSorting = useCallback((cardsToFilter: CardData[]) => {
    let filtered = cardsToFilter;

    if (filterOptions.owner) {
      filtered = filtered.filter(card => card.owner === filterOptions.owner);
    }

    if (filterOptions.rarity) {
      filtered = filtered.filter(card => card.rarity === filterOptions.rarity);
    }

    if (filterOptions.locked) {
      const shouldBeLocked = filterOptions.locked === 'locked';
      filtered = filtered.filter(card => Boolean(card.locked) === shouldBeLocked);
    }

    if (filterOptions.characterName) {
      filtered = filtered.filter(card => card.base_name === filterOptions.characterName);
    }

    if (filterOptions.setName) {
      filtered = filtered.filter(card => card.set_name === filterOptions.setName);
    }

    const sorted = [...filtered].sort((a, b) => {
      let aValue: string | number;
      let bValue: string | number;

      switch (sortOptions.field) {
        case 'rarity': {
          const rarityArray = [...RARITY_SEQUENCE] as string[];
          const aIndex = rarityArray.indexOf(a.rarity);
          const bIndex = rarityArray.indexOf(b.rarity);
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
  }, [filterOptions, sortOptions]);

  const baseDisplayedCards = useMemo(() => {
    if (isTradeMode && selectedCardForTrade) {
      return allCards.filter((card) =>
        card.id !== selectedCardForTrade.id &&
        (currentUserId == null || card.user_id !== currentUserId)
      );
    }
    return allCards;
  }, [isTradeMode, selectedCardForTrade, allCards, currentUserId]);

  const displayedCards = useMemo(
    () => applyFiltersAndSorting(baseDisplayedCards),
    [baseDisplayedCards, applyFiltersAndSorting]
  );

  // Apply filtering and sorting for current view grid
  const applyCurrentGridFiltersAndSorting = useCallback((cardsToFilter: CardData[]) => {
    let filtered = cardsToFilter;

    if (currentGridFilterOptions.rarity) {
      filtered = filtered.filter(card => card.rarity === currentGridFilterOptions.rarity);
    }

    if (currentGridFilterOptions.locked) {
      const shouldBeLocked = currentGridFilterOptions.locked === 'locked';
      filtered = filtered.filter(card => Boolean(card.locked) === shouldBeLocked);
    }

    if (currentGridFilterOptions.characterName) {
      filtered = filtered.filter(card => card.base_name === currentGridFilterOptions.characterName);
    }

    if (currentGridFilterOptions.setName) {
      filtered = filtered.filter(card => card.set_name === currentGridFilterOptions.setName);
    }

    const sorted = [...filtered].sort((a, b) => {
      let aValue: string | number;
      let bValue: string | number;

      switch (currentGridSortOptions.field) {
        case 'rarity': {
          const rarityArray = [...RARITY_SEQUENCE] as string[];
          const aIndex = rarityArray.indexOf(a.rarity);
          const bIndex = rarityArray.indexOf(b.rarity);
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
  }, [currentGridFilterOptions, currentGridSortOptions]);

  const filteredCurrentCards = useMemo(
    () => applyCurrentGridFiltersAndSorting(cards),
    [cards, applyCurrentGridFiltersAndSorting]
  );

  const shareEnabled = Boolean(initData);
  
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

  // Expand app on mount
  useEffect(() => {
    TelegramUtils.expandApp();
  }, []);

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
  
  // Memoized callback functions
  const handleTradeClick = useCallback(() => {
    if (enableTrade) {
      const tradeCard = modalCard || cards[currentIndex];
      
      if (!tradeCard) {
        return;
      }

      if (!tradeCard.chat_id) {
        TelegramUtils.showAlert('This card cannot be traded because it is not associated with a chat yet.');
        return;
      }

      if (modalCard) {
        closeModal();
      }

      setSelectedCardForTrade(tradeCard);
      setIsTradeGridActive(!hasChatScope);
      setView('all');
    }
  }, [cards, currentIndex, modalCard, enableTrade, hasChatScope, closeModal]);

  const handleSelectClick = useCallback(() => {
    if (selectedCardForTrade && modalCard) {
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
            TelegramUtils.closeApp();
          } else {
            const errorData = await response.json();
            TelegramUtils.showAlert(`Trade request failed: ${errorData.detail || 'Unknown error'}`);
          }
        } catch (tradeError) {
          console.error('Trade API error:', tradeError);
          TelegramUtils.showAlert('Trade request failed: Network error');
        }
      };

      executeTrade();
      switchToCurrentView();
    }
  }, [selectedCardForTrade, modalCard, initData, switchToCurrentView]);

  const handleCurrentTabClick = useCallback(() => {
    const preserveAllFilters = !isTradeMode;
    switchToCurrentView({ preserveAllFilters });
  }, [isTradeMode, switchToCurrentView]);

  const handleAllTabClick = useCallback(() => {
    setIsTradeGridActive(false);
    setSelectedCardForTrade(null);
    setView('all');
  }, []);

  const handleProfileTabClick = useCallback(() => {
    setIsTradeGridActive(false);
    setSelectedCardForTrade(null);
    setView('profile');
  }, []);

  const handleFilterChange = useCallback((newFilters: FilterOptions) => {
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
    try {
      await ApiService.shareCard(cardId, currentUserId, initData);
      TelegramUtils.showAlert('Shared to chat!');
    } catch (err) {
      console.error('Share card error:', err);
      const message = err instanceof Error ? err.message : 'Failed to share card.';
      TelegramUtils.showAlert(message);
    }
  }, [initData, currentUserId]);

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
    const targetCard = modalCard || cards[currentIndex];
    if (!targetCard) return;

    if (!targetCard.chat_id) {
      TelegramUtils.showAlert('Unable to burn this card because it is not associated with a chat yet.');
      return;
    }

    setShowBurnDialog(true);
  };

  const handleBurnConfirm = async () => {
    if (burningCard) return;

    const targetCard = modalCard || cards[currentIndex];
    if (!targetCard) return;

    const targetChatId = targetCard.chat_id;
    if (!targetChatId) {
      TelegramUtils.showAlert('Unable to burn this card because it is not associated with a chat yet.');
      return;
    }

    try {
      setBurningCard(true);
      
      const result = await ApiService.burnCard(
        targetCard.id,
        currentUserId,
        targetChatId,
        initData
      );

      const cardName = `${targetCard.modifier} ${targetCard.base_name}`.trim();
      const burnResult = {
        rarity: targetCard.rarity,
        cardName,
        spinsAwarded: result.spins_awarded,
        newSpinTotal: result.new_spin_total,
        cardId: targetCard.id,
        burnedCardIndex: cards.findIndex((c: CardData) => c.id === targetCard.id),
      };

      burnResultRef.current = burnResult;

      setShowBurnDialog(false);
      setTriggerBurn(true);
      setIsBurningInProgress(true);

    } catch (burnError) {
      console.error('Failed to burn card:', burnError);
      setShowBurnDialog(false);
      setBurningCard(false);
      TelegramUtils.showAlert(burnError instanceof Error ? burnError.message : 'Failed to burn card');
    }
  };

  const handleBurnComplete = async () => {
    setTriggerBurn(false);
    setBurningCard(false);
    setIsBurningInProgress(false);

    const burnResult = burnResultRef.current;
    if (!burnResult) return;

    burnResultRef.current = null;

    if (modalCard) {
      closeModal();
    } else if (burnResult.burnedCardIndex !== -1) {
      if (cards.length > 1) {
        if (burnResult.burnedCardIndex === cards.length - 1) {
          setCurrentIndex(Math.max(0, burnResult.burnedCardIndex - 1));
        }
      } else {
        setCurrentIndex(0);
      }
    }

    const notification = `${burnResult.rarity} ${burnResult.cardName} burned!\n\nReceived ${burnResult.spinsAwarded} spins\n\nBalance: ${burnResult.newSpinTotal}`;
    TelegramUtils.showAlert(notification);

    await refreshCardsData();
  };

  const handleBurnCancel = () => {
    setShowBurnDialog(false);
  };

  const handleLockClick = () => {
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

  const updateCardLockState = (cardId: number, locked: boolean) => {
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
  };

  const handleLockConfirm = async () => {
    if (lockingCard) return;

    const targetCard = modalCard || cards[currentIndex];
    if (!targetCard) return;

    const targetChatId = targetCard.chat_id;
    if (!targetChatId) {
      TelegramUtils.showAlert('Unable to lock this card because it is not associated with a chat yet.');
      return;
    }

    try {
      setLockingCard(true);
      const isCurrentlyLocked = targetCard.locked || false;
      const result = await ApiService.lockCard(
        targetCard.id,
        currentUserId,
        targetChatId,
        !isCurrentlyLocked,
        initData
      );

      setChatProfiles(prev => {
        const currentProfile = prev[targetChatId]?.profile;
        if (!currentProfile) return prev;
        
        return {
          ...prev,
          [targetChatId]: {
            ...prev[targetChatId],
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
    } catch (lockError) {
      console.error('Failed to lock/unlock card:', lockError);
      setChatProfiles(prev => {
        const existing = prev[targetChatId];
        const message = lockError instanceof Error ? lockError.message : 'Failed to lock/unlock card';
        return {
          ...prev,
          [targetChatId]: existing
            ? { ...existing, loading: false, error: message }
            : { profile: null, loading: false, error: message }
        };
      });
      TelegramUtils.showAlert(lockError instanceof Error ? lockError.message : 'Failed to lock/unlock card');
    } finally {
      setLockingCard(false);
      setShowLockDialog(false);
    }
  };

  const handleLockCancel = () => {
    setShowLockDialog(false);
  };

  // Action Panel logic
  const getActionButtons = (): ActionButton[] => {
    if (loading || error) {
      return [];
    }

    const buttons: ActionButton[] = [];
    const shouldDisableActions = burningCard || isBurningInProgress;

    if (isOwnCollection && cards.length > 0 && view === 'current' && !selectedCardForTrade && modalCard) {
      const currentCard = modalCard;
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

    if (isOwnCollection && enableTrade && cards.length > 0 && view === 'current' && !selectedCardForTrade && modalCard) {
      buttons.push({
        id: 'trade',
        text: 'Trade',
        onClick: handleTradeClick,
        variant: 'primary',
        disabled: shouldDisableActions
      });
    } else if (enableTrade && selectedCardForTrade && modalCard && view === 'all' && modalCard.owner && modalCard.owner !== TelegramUtils.getCurrentUsername()) {
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
    if (collectionDisplayName && collectionDisplayName.trim().length > 0) {
      return collectionDisplayName;
    }
    if (collectionUsername && collectionUsername.trim().length > 0) {
      return `@${collectionUsername}`;
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
  if (loading) {
    return (
      <div className="app-container">
        <Title title="Loading..." loading fullscreen />
      </div>
    );
  }

  // Error state
  if (error) {
    return <div className="app-container"><h1>Error: {error}</h1></div>;
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
        <CollectionLayout
          view={view}
          hasChatScope={hasChatScope}
          isTradeGridActive={isTradeGridActive}
          isTradeView={isTradeView}
          tradeCardName={tradeCardName}
          collectionOwnerLabel={collectionOwnerLabel}
          tabs={{
            onCurrentTabClick: handleCurrentTabClick,
            onAllTabClick: handleAllTabClick,
            onProfileTabClick: handleProfileTabClick
          }}
          profileView={viewedProfile}
          currentView={{
            cards,
            filteredCards: filteredCurrentCards,
            initData,
            onOpenModal: openModal,
            currentGridFilterOptions,
            currentGridSortOptions,
            onCurrentGridFilterChange: handleCurrentGridFilterChange,
            onCurrentGridSortChange: handleCurrentGridSortChange,
            collectionOwnerLabel,
            isOwnCollection,
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
          isActionPanelVisible={isActionPanelVisible}
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
