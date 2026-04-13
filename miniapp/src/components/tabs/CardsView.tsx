import { useState, useCallback, useEffect, useRef, useMemo } from 'react';

// Components
import { CardModal, CardGrid, FilterSortControls } from '@/components/cards';
import { ActionPanel } from '@/components/common';
import Loading from '@/components/common/Loading';
import { LockConfirmDialog } from '@/components/dialogs';
import type { ActionButton } from '@/components/common';
import TradeHeader from '@/components/common/TradeHeader';

// Hooks
import {
  useOrientation,
  useModal,
  useCollectionCards,
  useCardFiltering,
  useTradeOptions,
  useTradeExecution,
} from '@/hooks';

// Services
import { ApiService } from '@/services/api';

// Utils
import { TelegramUtils } from '@/utils/telegram';

// Types
import type { CardData, AspectConfigResponse, ClaimBalanceState, TradeOffer } from '@/types';

interface CardsViewProps {
  currentUserId: number;
  chatId: string | null;
  initData: string;
  ownerLabel: string | null;
  initialConfig?: AspectConfigResponse;
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
  onRefresh?: () => Promise<void>;
  // Trade mode (managed by CollectionTab)
  tradeOffer?: TradeOffer | null;
  onTradeInitiate?: (offer: TradeOffer) => void;
}

const CardsView = ({
  currentUserId,
  chatId,
  initData,
  ownerLabel,
  initialConfig,
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
  onRefresh: onRefreshProp,
  // Trade mode props
  tradeOffer,
  onTradeInitiate,
}: CardsViewProps) => {
  const collectionOwnerLabel = ownerLabel ?? 'Collection';
  const isTradeMode = Boolean(tradeOffer);

  const {
    cards: hookCards,
    loading: hookLoading,
    error: hookError,
    refetch: refetchCards,
    updateCard,
  } = useCollectionCards(initData, chatId, targetUserId ?? currentUserId, {
    initialCards,
    enabled: !isReadOnly && !isTradeMode,
  });

  // Trade mode: fetch options
  const {
    items: tradeCards,
    loading: tradeLoading,
    error: tradeError,
    refetch: refetchTradeCards,
  } = useTradeOptions<CardData>(tradeOffer, initData, 'card');

  // Choose data source based on mode
  const cards = useMemo(
    () => isTradeMode ? tradeCards : (isReadOnly ? (allCardsProp ?? []) : hookCards),
    [isTradeMode, tradeCards, isReadOnly, allCardsProp, hookCards],
  );
  const loading = isTradeMode ? tradeLoading : (isReadOnly ? false : hookLoading);
  const error = isTradeMode ? tradeError : (isReadOnly ? null : hookError);
  const isOwnCollection = isReadOnly || isTradeMode ? false : (isOwnCollectionProp ?? true);
  const enableTrade = isReadOnly || isTradeMode ? false : (enableTradeProp ?? false);

  const { orientation, orientationKey } = useOrientation({ enabled: true });

  // Lock dialog state
  const [showLockDialog, setShowLockDialog] = useState(false);
  const [lockProcessing, setLockProcessing] = useState(false);
  const [claimState, setClaimState] = useState<ClaimBalanceState>({
    balance: null,
    loading: false,
  });

  const config = initialConfig ?? null;

  // Profile loading for card owners
  const [chatProfiles, setChatProfiles] = useState<Record<string, { profile: import('@/types').UserProfile | null; loading: boolean; error?: string }>>({});
  const profileRequestsRef = useRef<Map<string, Promise<import('@/types').UserProfile | null>>>(new Map());
  const pendingChatIdsRef = useRef<Set<string>>(new Set());

  const ensureUserProfile = useCallback(async (
    profileChatId: string,
    options: { force?: boolean } = {}
  ): Promise<import('@/types').UserProfile | null> => {
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

  // Filtering
  const currentFiltering = useCardFiltering(cards, { includeOwnerFilter: isReadOnly || isTradeMode });
  const filteredCurrentCards = currentFiltering.displayedCards;

  const shareEnabled = Boolean(initData) && !isTradeMode;

  // Feature hooks
  const { showModal, modalCard, openModal, closeModal, updateModalCard } = useModal();

  // Trade mode: execution
  const { executing: tradeExecuting, execute: executeTradeSelection } = useTradeExecution(
    tradeOffer, initData, 'card', modalCard?.id ?? null,
  );

  const lockCost = modalCard && config
    ? config.lock_costs[modalCard.rarity] ?? 0
    : 0;

  // Trade initiation (from normal collection mode)
  const handleTradeClick = useCallback(() => {
    if (enableTrade) {
      const card = modalCard || cards[0];
      if (!card) return;

      if (!card.chat_id) {
        TelegramUtils.showAlert('This card cannot be traded because it is not associated with a chat yet.');
        return;
      }

      closeModal();
      const cardName = [card.modifier, card.base_name].filter(Boolean).join(' ');
      onTradeInitiate?.({ type: 'card', id: card.id, title: cardName, rarity: card.rarity });
    }
  }, [cards, modalCard, enableTrade, closeModal, onTradeInitiate]);

  // Trade selection (from trade mode — select a card to trade for)

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

  // Action Panel
  const actionButtons = useMemo<ActionButton[]>(() => {
    if (loading || error) return [];

    // Trade mode: show Select button for other users' cards
    if (isTradeMode && modalCard && showModal && modalCard.user_id !== currentUserId) {
      return [{
        id: 'select',
        text: tradeExecuting ? 'Loading...' : 'Select',
        onClick: executeTradeSelection,
        variant: 'trade-blue' as const,
        disabled: tradeExecuting,
      }];
    }

    if (isReadOnly || isTradeMode) return [];

    const buttons: ActionButton[] = [];

    if (isOwnCollection && modalCard) {
      buttons.push({
        id: 'lock',
        text: modalCard.locked ? 'Unlock' : 'Lock',
        onClick: handleLockClick,
        variant: 'lock-grey',
      });
    }

    if (isOwnCollection && enableTrade && cards.length > 0 && modalCard) {
      buttons.push({
        id: 'trade', text: 'Trade', onClick: handleTradeClick,
        variant: 'trade-blue'
      });
    }

    return buttons;
  }, [
    loading, error, isTradeMode, isReadOnly, tradeExecuting,
    isOwnCollection, cards.length, modalCard, showModal, enableTrade, currentUserId,
    handleLockClick, handleTradeClick, executeTradeSelection,
  ]);

  const isActionPanelVisible = actionButtons.length > 0;

  if (loading) {
    return <Loading message={isTradeMode ? 'Loading trade options...' : 'Loading collection...'} />;
  }

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
        <div className="app-content">
          {isTradeMode && tradeOffer && (
            <TradeHeader title={tradeOffer.title} rarity={tradeOffer.rarity} />
          )}
          {cards.length > 0 ? (
            <>
              <FilterSortControls
                cards={cards}
                filterOptions={currentFiltering.filterOptions}
                sortOptions={currentFiltering.sortOptions}
                onFilterChange={currentFiltering.onFilterChange}
                onSortChange={currentFiltering.onSortChange}
                showOwnerFilter={isReadOnly || isTradeMode}
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
                  onRefresh={isTradeMode ? refetchTradeCards : (onRefreshProp ?? (!isReadOnly ? refetchCards : undefined))}
                />
              )}
            </>
          ) : (
            <p>
              {isTradeMode
                ? 'No cards are available to trade for in this chat.'
                : isOwnCollection
                  ? "You don't own any cards yet."
                  : `${collectionOwnerLabel} doesn't own any cards yet.`}
            </p>
          )}
        </div>
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
