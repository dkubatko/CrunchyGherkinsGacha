import { useState, useCallback, useEffect, useRef, useMemo } from 'react';

// Components
import { CardModal, CardGrid, FilterSortControls } from '@/components/cards';
import { ActionPanel, Title } from '@/components/common';
import Loading from '@/components/common/Loading';
import { BurnConfirmDialog, LockConfirmDialog } from '@/components/dialogs';
import type { ActionButton } from '@/components/common';

// Hooks
import {
  useAllCards,
  useOrientation,
  useModal,
  useSwipeHandlers,
  useCollectionCards,
  useCardFiltering,
  DEFAULT_FILTER_OPTIONS,
  DEFAULT_SORT_OPTIONS,
} from '@/hooks';

// Utils
import { TelegramUtils } from '@/utils/telegram';

// Services
import { ApiService } from '@/services/api';

// Types
import type { CardData, ClaimBalanceState, ProfileState, UserProfile } from '@/types';

interface CollectionTabProps {
  currentUserId: number;
  targetUserId: number;
  chatId: string | null;
  isOwnCollection: boolean;
  enableTrade: boolean;
  initData: string;
}

const CollectionTab = ({
  currentUserId,
  targetUserId: initialTargetUserId,
  chatId,
  isOwnCollection: initialIsOwnCollection,
  enableTrade: initialEnableTrade,
  initData,
}: CollectionTabProps) => {
  // Core data hooks
  const {
    cards,
    loading,
    error,
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
  const [selectedCardForTrade, setSelectedCardForTrade] = useState<CardData | null>(null);
  const [showBurnDialog, setShowBurnDialog] = useState(false);
  const [showLockDialog, setShowLockDialog] = useState(false);
  const [lockingCard, setLockingCard] = useState(false);
  const [burningCard, setBurningCard] = useState(false);
  const [triggerBurn, setTriggerBurn] = useState(false);
  const [isBurningInProgress, setIsBurningInProgress] = useState(false);
  const [chatProfiles, setChatProfiles] = useState<Record<string, ProfileState>>({});
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
  const [isTradeView, setIsTradeView] = useState(false);

  const isTradeMode = Boolean(selectedCardForTrade);
  const activeTradeCardId = isTradeMode && selectedCardForTrade ? selectedCardForTrade.id : null;
  const cardsScopeChatId = isTradeMode && selectedCardForTrade?.chat_id
    ? selectedCardForTrade.chat_id
    : chatId;
  const shouldFetchAllCards = activeTradeCardId !== null;

  const ensureUserProfile = useCallback(async (
    profileChatId: string,
    options: { force?: boolean } = {}
  ): Promise<UserProfile | null> => {
    if (!profileChatId) return null;

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
          [profileChatId]: { profile: result, loading: false, error: undefined }
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
    if (!card.chat_id) return;
    void ensureUserProfile(card.chat_id);
  }, [ensureUserProfile]);

  useEffect(() => {
    if (pendingChatIdsRef.current.size === 0) return;
    const queuedChatIds = Array.from(pendingChatIdsRef.current);
    pendingChatIdsRef.current.clear();
    queuedChatIds.forEach(queuedChatId => {
      void ensureUserProfile(queuedChatId, { force: true });
    });
  }, [ensureUserProfile]);

  // Load card config on first render
  useEffect(() => {
    if (cardConfigLoadedRef.current) return;
    cardConfigLoadedRef.current = true;

    const loadCardConfig = async () => {
      try {
        const config = await ApiService.fetchCardConfig(initData);
        setBurnRewards(config.burn_rewards);
        setLockCosts(config.lock_costs);
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

  const baseDisplayedCards = useMemo(() => {
    if (isTradeMode && selectedCardForTrade) {
      return allCards.filter((card) =>
        card.id !== selectedCardForTrade.id &&
        (currentUserId == null || card.user_id !== currentUserId)
      );
    }
    return allCards;
  }, [isTradeMode, selectedCardForTrade, allCards, currentUserId]);

  const tradeFiltering = useCardFiltering(baseDisplayedCards);
  const currentFiltering = useCardFiltering(cards, { includeOwnerFilter: false });
  const displayedCards = tradeFiltering.displayedCards;
  const filteredCurrentCards = currentFiltering.displayedCards;

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

  const switchToCurrentView = useCallback((options?: { preserveAllFilters?: boolean }) => {
    setSelectedCardForTrade(null);
    setIsTradeView(false);
    closeModal();
    if (!options?.preserveAllFilters) {
      tradeFiltering.setFilterOptions(DEFAULT_FILTER_OPTIONS);
      tradeFiltering.setSortOptions(DEFAULT_SORT_OPTIONS);
    }
    TelegramUtils.hideBackButton();
  }, [closeModal, tradeFiltering]);

  const switchToCurrentViewRef = useRef(switchToCurrentView);
  useEffect(() => {
    switchToCurrentViewRef.current = switchToCurrentView;
  }, [switchToCurrentView]);

  // Trade handlers
  const handleTradeClick = useCallback(() => {
    if (enableTrade) {
      const tradeCard = modalCard || cards[currentIndex];
      if (!tradeCard) return;

      if (!tradeCard.chat_id) {
        TelegramUtils.showAlert('This card cannot be traded because it is not associated with a chat yet.');
        return;
      }

      if (modalCard) closeModal();

      setSelectedCardForTrade(tradeCard);
      setIsTradeView(true);
    }
  }, [cards, currentIndex, modalCard, enableTrade, closeModal]);

  const handleSelectClick = useCallback(() => {
    if (selectedCardForTrade && modalCard) {
      const executeTrade = async () => {
        try {
          const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com';
          const response = await fetch(`${apiBaseUrl}/trade/${selectedCardForTrade.id}/${modalCard.id}`, {
            method: 'POST',
            headers: { 'Authorization': `tma ${initData}` }
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

  // Burn handlers
  const handleBurnClick = useCallback(() => {
    const targetCard = modalCard || cards[currentIndex];
    if (!targetCard) return;
    if (!targetCard.chat_id) {
      TelegramUtils.showAlert('Unable to burn this card because it is not associated with a chat yet.');
      return;
    }
    setShowBurnDialog(true);
  }, [modalCard, cards, currentIndex]);

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
      const result = await ApiService.burnCard(targetCard.id, currentUserId, targetChatId, initData);
      const cardName = `${targetCard.modifier} ${targetCard.base_name}`.trim();
      burnResultRef.current = {
        rarity: targetCard.rarity,
        cardName,
        spinsAwarded: result.spins_awarded,
        newSpinTotal: result.new_spin_total,
        cardId: targetCard.id,
        burnedCardIndex: cards.findIndex((c: CardData) => c.id === targetCard.id),
      };

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

  const handleBurnCancel = () => setShowBurnDialog(false);

  // Lock handlers
  const handleLockClick = useCallback(() => {
    const targetCard = modalCard || cards[currentIndex];
    if (!targetCard) return;
    if (!targetCard.chat_id) {
      TelegramUtils.showAlert('Unable to lock this card because it is not associated with a chat yet.');
      return;
    }
    const rarityLockCost = Math.max(1, lockCosts?.[targetCard.rarity] ?? 1);
    if (rarityLockCost > 0) void ensureUserProfile(targetCard.chat_id);
    setShowLockDialog(true);
  }, [modalCard, cards, currentIndex, lockCosts, ensureUserProfile]);

  const updateCardLockState = (cardId: number, locked: boolean) => {
    if (modalCard && modalCard.id === cardId) updateModalCard({ locked });
    updateCardInCollection(cardId, { locked });
    updateAllCardsCollection(cardId, { locked });
    if (selectedCardForTrade?.id === cardId) {
      setSelectedCardForTrade((prev) => prev ? { ...prev, locked } : prev);
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
        targetCard.id, currentUserId, targetChatId, !isCurrentlyLocked, initData
      );

      setChatProfiles(prev => {
        const currentProfile = prev[targetChatId]?.profile;
        if (!currentProfile) return prev;
        return {
          ...prev,
          [targetChatId]: {
            ...prev[targetChatId],
            profile: { ...currentProfile, claim_balance: result.balance }
          }
        };
      });

      setLockingCard(false);
      setShowLockDialog(false);
      updateCardLockState(targetCard.id, result.locked);

      if (result.lock_cost !== undefined) {
        setLockCosts(prev => ({ ...(prev ?? {}), [targetCard.rarity]: result.lock_cost }));
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

  const handleLockCancel = () => setShowLockDialog(false);

  // Action Panel logic
  const actionButtons = useMemo<ActionButton[]>(() => {
    if (loading || error) return [];
    const buttons: ActionButton[] = [];
    const shouldDisableActions = burningCard || isBurningInProgress;

    if (isOwnCollection && cards.length > 0 && !isTradeView && !selectedCardForTrade && modalCard) {
      if (modalCard.chat_id) {
        buttons.push({
          id: 'burn', text: 'Burn', onClick: handleBurnClick,
          variant: 'burn-red', disabled: shouldDisableActions
        });
        buttons.push({
          id: 'lock', text: modalCard.locked ? 'Unlock' : 'Lock',
          onClick: handleLockClick, variant: 'lock-grey',
          disabled: shouldDisableActions || lockingCard
        });
      }
    }

    if (isOwnCollection && enableTrade && cards.length > 0 && !isTradeView && !selectedCardForTrade && modalCard) {
      buttons.push({
        id: 'trade', text: 'Trade', onClick: handleTradeClick,
        variant: 'primary', disabled: shouldDisableActions
      });
    } else if (enableTrade && selectedCardForTrade && modalCard && isTradeView &&
      modalCard.owner && modalCard.owner !== TelegramUtils.getCurrentUsername()) {
      buttons.push({
        id: 'select', text: 'Select', onClick: handleSelectClick,
        variant: 'primary', disabled: shouldDisableActions
      });
    }

    return buttons;
  }, [
    loading,
    error,
    burningCard,
    isBurningInProgress,
    isOwnCollection,
    cards.length,
    isTradeView,
    selectedCardForTrade,
    modalCard,
    handleBurnClick,
    handleLockClick,
    lockingCard,
    enableTrade,
    handleTradeClick,
    handleSelectClick
  ]);

  const isActionPanelVisible = actionButtons.length > 0;

  const collectionOwnerLabel = (() => {
    if (collectionDisplayName && collectionDisplayName.trim().length > 0) return collectionDisplayName;
    if (collectionUsername && collectionUsername.trim().length > 0) return `@${collectionUsername}`;
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
    return <Loading message="Loading collection..." />;
  }

  // Error state
  if (error) {
    return (
      <div className="error-container">
        <h2>Error</h2>
        <p>{error}</p>
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
      <div
        className={`collection-tab-content ${isActionPanelVisible ? 'with-action-panel' : ''}`}
        {...(!isBurningInProgress && !isTradeView ? swipeHandlers : {})}
      >
        {/* Trade view: selecting a card to trade for */}
        {isTradeView ? (
          <div className="app-content">
            <Title
              title={tradeCardName ? `Trade for ${tradeCardName}` : 'Trade'}
            />
            {allCardsLoading ? (
              <Loading message="Loading trade options..." />
            ) : allCardsError ? (
              <div className="error-container">
                <h2>Error loading trade options</h2>
                <p>{allCardsError}</p>
                <button onClick={() => { void refetchAllCards(); }}>Retry</button>
              </div>
            ) : baseDisplayedCards.length === 0 ? (
              <div className="no-cards-container">
                <h2>No trade options</h2>
                <p>No other cards are available in this chat right now.</p>
              </div>
            ) : (
              <>
                <FilterSortControls
                  cards={baseDisplayedCards}
                  filterOptions={tradeFiltering.filterOptions}
                  sortOptions={tradeFiltering.sortOptions}
                  onFilterChange={tradeFiltering.onFilterChange}
                  onSortChange={tradeFiltering.onSortChange}
                  counter={{
                    current: displayedCards.length,
                    total: baseDisplayedCards.length
                  }}
                />
                {displayedCards.length === 0 ? (
                  <div className="no-cards-container">
                    <h2>No cards match your filters</h2>
                    <p>Try adjusting your filter settings to see more cards.</p>
                  </div>
                ) : (
                  <CardGrid
                    cards={displayedCards}
                    onCardClick={openModal}
                    initData={initData}
                  />
                )}
              </>
            )}
          </div>
        ) : (
          /* Normal collection view */
          <div className="app-content">
            <Title title={`${collectionOwnerLabel}'s collection`} />
            {cards.length > 0 ? (
              <>
                <FilterSortControls
                  cards={cards}
                  filterOptions={currentFiltering.filterOptions}
                  sortOptions={currentFiltering.sortOptions}
                  onFilterChange={currentFiltering.onFilterChange}
                  onSortChange={currentFiltering.onSortChange}
                  showOwnerFilter={false}
                  counter={{
                    current: filteredCurrentCards.length,
                    total: cards.length
                  }}
                />
                {filteredCurrentCards.length === 0 ? (
                  <div className="no-cards-container">
                    <h2>No cards match your filter</h2>
                    <p>Try selecting a different rarity or clearing the filter.</p>
                  </div>
                ) : (
                  <CardGrid
                    cards={filteredCurrentCards}
                    onCardClick={openModal}
                    initData={initData}
                  />
                )}
              </>
            ) : (
              <p>
                {isOwnCollection
                  ? "You don't own any cards yet."
                  : `${collectionOwnerLabel} doesn't own any cards yet.`}
              </p>
            )}
          </div>
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
    </>
  );
};

export default CollectionTab;
