import { useState, useCallback, useEffect, useRef, useMemo } from 'react';

// Components
import { CardModal, CardGrid, FilterSortControls } from '@/components/cards';
import { ActionPanel, Title } from '@/components/common';
import Loading from '@/components/common/Loading';
import { LockConfirmDialog } from '@/components/dialogs';
import type { ActionButton } from '@/components/common';

// Hooks
import {
  useAllCards,
  useOrientation,
  useModal,
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
import type { CardData, ProfileState, UserProfile, AspectConfigResponse, ClaimBalanceState } from '@/types';

interface CardsViewProps {
  currentUserId: number;
  chatId: string | null;
  initData: string;
  ownerLabel: string | null;
  initialConfig?: AspectConfigResponse;
  isActive?: boolean;
  onLockSwipe?: (locked: boolean) => void;
  // Mutable mode (user's collection)
  targetUserId?: number;
  isOwnCollection?: boolean;
  enableTrade?: boolean;
  initialCards?: CardData[];
  onCardUpdate?: (cardId: number, updates: Partial<CardData>) => void;
  onClaimPointsUpdate?: (count: number) => void;
  // Read-only mode (all cards in chat)
  isReadOnly?: boolean;
  allCards?: CardData[];
}

const CardsView = ({
  currentUserId,
  chatId,
  initData,
  ownerLabel,
  initialConfig,
  onLockSwipe,
  // Mutable mode props
  targetUserId,
  isOwnCollection: isOwnCollectionProp,
  enableTrade: enableTradeProp,
  initialCards,
  onCardUpdate,
  onClaimPointsUpdate,
  // Read-only mode props
  isReadOnly = false,
  allCards: allCardsProp,
}: CardsViewProps) => {
  const collectionOwnerLabel = ownerLabel ?? 'Collection';

  // For read-only mode, use the provided allCards directly
  // For mutable mode, use useCollectionCards hook (ownership resolved by hub)
  const {
    cards: hookCards,
    loading: hookLoading,
    error: hookError,
    updateCard,
  } = useCollectionCards(initData, chatId, targetUserId ?? currentUserId, {
    initialCards,
    enabled: !isReadOnly,
  });

  // In read-only mode, use props; in mutable mode, use hook values
  const cards = useMemo(
    () => (isReadOnly ? (allCardsProp ?? []) : hookCards),
    [isReadOnly, allCardsProp, hookCards]
  );
  const loading = isReadOnly ? false : hookLoading;
  const error = isReadOnly ? null : hookError;
  const isOwnCollection = isReadOnly ? false : (isOwnCollectionProp ?? true);
  const enableTrade = isReadOnly ? false : (enableTradeProp ?? false);

  // Only enable orientation tracking for card tilt effects
  const { orientation, orientationKey } = useOrientation({ enabled: true });

  // UI state
  const [currentIndex] = useState(0);
  const [selectedCardForTrade, setSelectedCardForTrade] = useState<CardData | null>(null);
  const [chatProfiles, setChatProfiles] = useState<Record<string, ProfileState>>({});
  const profileRequestsRef = useRef<Map<string, Promise<UserProfile | null>>>(new Map());
  const pendingChatIdsRef = useRef<Set<string>>(new Set());
  const [isTradeView, setIsTradeView] = useState(false);

  const isTradeMode = Boolean(selectedCardForTrade);
  const activeTradeCardId = isTradeMode && selectedCardForTrade ? selectedCardForTrade.id : null;
  const cardsScopeChatId = isTradeMode && selectedCardForTrade?.chat_id
    ? selectedCardForTrade.chat_id
    : chatId;
  const shouldFetchAllCards = activeTradeCardId !== null;

  // Lock dialog state
  const [showLockDialog, setShowLockDialog] = useState(false);
  const [lockProcessing, setLockProcessing] = useState(false);
  const [claimState, setClaimState] = useState<ClaimBalanceState>({
    balance: null,
    loading: false,
  });

  // Config (lock costs) — prefetched from hub (use prop directly, no state needed)
  const config = initialConfig ?? null;

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

  const {
    allCards,
    loading: allCardsLoading,
    error: allCardsError,
    refetch: refetchAllCards,
  } = useAllCards(initData, cardsScopeChatId, {
    enabled: shouldFetchAllCards,
    tradeCardId: activeTradeCardId
  });

  const tradeCardName = selectedCardForTrade
    ? [selectedCardForTrade.modifier, selectedCardForTrade.base_name].filter(Boolean).join(' ')
    : null;

  const baseDisplayedCards = useMemo(() => {
    if (isTradeMode && selectedCardForTrade) {
      return allCards.filter((card) =>
        card.id !== selectedCardForTrade.id &&
        card.user_id !== currentUserId
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

  const lockCost = modalCard && config
    ? config.lock_costs[modalCard.rarity] ?? 0
    : 0;

  const switchToCurrentView = useCallback((options?: { preserveAllFilters?: boolean }) => {
    setSelectedCardForTrade(null);
    setIsTradeView(false);
    onLockSwipe?.(false);
    closeModal();
    if (!options?.preserveAllFilters) {
      tradeFiltering.setFilterOptions(DEFAULT_FILTER_OPTIONS);
      tradeFiltering.setSortOptions(DEFAULT_SORT_OPTIONS);
    }
    TelegramUtils.hideBackButton();
  }, [closeModal, tradeFiltering, onLockSwipe]);

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
      onLockSwipe?.(true);
    }
  }, [cards, currentIndex, modalCard, enableTrade, closeModal, onLockSwipe]);

  const handleSelectClick = useCallback(() => {
    if (selectedCardForTrade && modalCard) {
      const executeTrade = async () => {
        try {
          const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api';
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

  // ── Lock / Unlock ──
  const handleLockClick = useCallback(() => {
    if (!modalCard) return;
    setShowLockDialog(true);
  }, [modalCard]);

  const handleLockConfirm = useCallback(async () => {
    if (!modalCard || !chatId) return;
    setLockProcessing(true);
    try {
      const wantLock = !modalCard.locked;
      const result = await ApiService.lockCard(modalCard.id, currentUserId, chatId, wantLock, initData);
      setClaimState({ balance: result.balance, loading: false });
      onClaimPointsUpdate?.(result.balance);
      updateModalCard({ locked: result.locked });
      TelegramUtils.showAlert(result.message || (result.locked ? 'Locked!' : 'Unlocked!'));
      setShowLockDialog(false);
      // Client-side update — no refetch needed
      updateCard(modalCard.id, { locked: result.locked });
      onCardUpdate?.(modalCard.id, { locked: result.locked });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Lock/unlock failed';
      TelegramUtils.showAlert(msg);
    } finally {
      setLockProcessing(false);
    }
  }, [modalCard, chatId, currentUserId, initData, updateCard, updateModalCard, onCardUpdate, onClaimPointsUpdate]);

  const handleLockCancel = useCallback(() => setShowLockDialog(false), []);

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

  // Action Panel logic — disabled in read-only mode
  const actionButtons = useMemo<ActionButton[]>(() => {
    if (isReadOnly || loading || error) return [];
    const buttons: ActionButton[] = [];

    if (isOwnCollection && !isTradeView && !selectedCardForTrade && modalCard) {
      buttons.push({
        id: 'lock',
        text: modalCard.locked ? 'Unlock' : 'Lock',
        onClick: handleLockClick,
        variant: 'lock-grey',
      });
    }

    if (isOwnCollection && enableTrade && cards.length > 0 && !isTradeView && !selectedCardForTrade && modalCard) {
      buttons.push({
        id: 'trade', text: 'Trade', onClick: handleTradeClick,
        variant: 'trade-blue'
      });
    } else if (enableTrade && selectedCardForTrade && modalCard && isTradeView &&
      modalCard.owner && modalCard.owner !== TelegramUtils.getCurrentUsername()) {
      buttons.push({
        id: 'select', text: 'Select', onClick: handleSelectClick,
        variant: 'trade-blue'
      });
    }

    return buttons;
  }, [
    isReadOnly,
    loading,
    error,
    isOwnCollection,
    cards.length,
    isTradeView,
    selectedCardForTrade,
    modalCard,
    enableTrade,
    handleLockClick,
    handleTradeClick,
    handleSelectClick
  ]);

  const isActionPanelVisible = actionButtons.length > 0;

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

  return (
    <>
      <div
        className={`collection-tab-content ${isActionPanelVisible ? 'with-action-panel' : ''}`}
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
          onClose={closeModal}
          onShare={shareEnabled ? handleShareCard : undefined}
          onCardOpen={handleCardOpen}
          isActionPanelVisible={isActionPanelVisible}
        />
      )}

      {/* Lock confirmation */}
      <LockConfirmDialog
        isOpen={showLockDialog}
        locking={lockProcessing}
        card={modalCard}
        lockCost={lockCost}
        claimState={claimState}
        onConfirm={() => void handleLockConfirm()}
        onCancel={handleLockCancel}
      />

      {/* Action Panel */}
      <ActionPanel
        buttons={actionButtons}
        visible={isActionPanelVisible}
      />
    </>
  );
};

export default CardsView;
