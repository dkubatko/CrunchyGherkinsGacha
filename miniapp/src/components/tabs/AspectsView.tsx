import { useState, useCallback, useMemo, useRef } from 'react';
import './AspectsView.css';

// Components
import { AspectGrid, AspectModal, EquipCardSelector } from '@/components/aspects';
import { FilterSortControls } from '@/components/cards';
import { ActionPanel } from '@/components/common';
import TradeHeader from '@/components/common/TradeHeader';
import Loading from '@/components/common/Loading';
import { BurnConfirmDialog, LockConfirmDialog, EquipNameDialog } from '@/components/dialogs';
import type { ActionButton } from '@/components/common';

// Hooks
import { useCollectionAspects, useTradeOptions, useTradeExecution, useModal, useAutoOpenItem } from '@/hooks';
import { useAspectFiltering } from '@/hooks/useAspectFiltering';
import { useOrientation } from '@/hooks';

// Services
import { ApiService } from '@/services/api';

// Utils
import { TelegramUtils } from '@/utils/telegram';

// Types
import type { AspectData, AspectConfigResponse, ClaimBalanceState, CardData, TradeOffer } from '@/types';

interface AspectsViewProps {
  currentUserId: number;
  chatId: string | null;
  initData: string;
  ownerLabel: string | null;
  initialConfig?: AspectConfigResponse;
  // Mutable mode (user's aspects)
  targetUserId?: number;
  initialAspects?: AspectData[];
  onAspectUpdate?: (aspectId: number, updates: Partial<AspectData>) => void;
  onAspectRemove?: (aspectId: number) => void;
  onClaimPointsUpdate?: (count: number) => void;
  onSpinsUpdate?: (count: number) => void;
  // Read-only mode (all aspects in chat)
  isReadOnly?: boolean;
  allAspects?: AspectData[];
  onRefresh?: () => Promise<void>;
  // Trade mode (managed by CollectionTab)
  tradeOffer?: TradeOffer | null;
  onTradeInitiate?: (offer: TradeOffer) => void;
  // Deep-link request: open this aspect's modal once available
  pendingOpenAspectId?: number | null;
}

const AspectsView = ({
  currentUserId,
  chatId,
  initData,
  ownerLabel,
  initialConfig,
  // Mutable mode props
  targetUserId,
  initialAspects,
  onAspectUpdate,
  onAspectRemove,
  onClaimPointsUpdate,
  onSpinsUpdate,
  // Read-only mode props
  isReadOnly = false,
  allAspects: allAspectsProp,
  onRefresh: onRefreshProp,
  // Trade mode props
  tradeOffer,
  onTradeInitiate,
  pendingOpenAspectId,
}: AspectsViewProps) => {
  const isTradeMode = Boolean(tradeOffer);
  const collectionOwnerLabel = ownerLabel ?? 'Collection';

  const {
    aspects: hookAspects,
    loading: hookLoading,
    error: hookError,
    refetch,
    updateAspect,
    removeAspect,
  } = useCollectionAspects(initData, chatId, targetUserId, { initialAspects, enabled: !isReadOnly && !isTradeMode });

  // Trade mode: fetch options
  const {
    items: tradeAspects,
    loading: tradeLoading,
    error: tradeError,
    refetch: refetchTradeAspects,
  } = useTradeOptions<AspectData>(tradeOffer, initData, 'aspect');

  // Choose data source based on mode
  const aspects = isTradeMode ? tradeAspects : (isReadOnly ? (allAspectsProp ?? []) : hookAspects);
  const loading = isTradeMode ? tradeLoading : (isReadOnly ? false : hookLoading);
  const error = isTradeMode ? tradeError : (isReadOnly ? null : hookError);

  const { orientation, orientationKey } = useOrientation({ enabled: true });
  const isOwnCollection = isReadOnly || isTradeMode ? false : (!targetUserId || targetUserId === currentUserId);

  // Filtering / sorting
  const {
    displayedAspects,
    filterOptions,
    sortOptions,
    filterValues,
    onFilterChange,
    onSortChange,
  } = useAspectFiltering(aspects);

  // Trade mode: execution (selectedAspect referenced below; declared by useModal further down).
  // We forward the modal id once it's available — closures inside useTradeExecution will pick it up.

  const config = initialConfig ?? null;

  // Burn dialog
  const [showBurnDialog, setShowBurnDialog] = useState(false);
  const [burnProcessing, setBurnProcessing] = useState(false);

  // Lock dialog
  const [showLockDialog, setShowLockDialog] = useState(false);
  const [lockProcessing, setLockProcessing] = useState(false);
  const [claimState, setClaimState] = useState<ClaimBalanceState>({
    balance: null,
    loading: false,
  });

  // Equip flow state
  const [showEquipSelector, setShowEquipSelector] = useState(false);
  const [equipSelectedCard, setEquipSelectedCard] = useState<CardData | null>(null);
  const [showEquipNameDialog, setShowEquipNameDialog] = useState(false);
  const [equipProcessing, setEquipProcessing] = useState(false);

  // Burn animation state
  const [triggerBurn, setTriggerBurn] = useState(false);
  const [isBurning, setIsBurning] = useState(false);
  const burnResultRef = useRef<string>('');

  // Modal state (shared generic hook)
  const {
    showModal,
    modalItem: selectedAspect,
    openModal,
    closeModal,
    setOpen: setModalOpen,
    updateModalItem: updateSelectedAspect,
  } = useModal<AspectData>();

  // Trade mode: execution
  const { executing: tradeExecuting, execute: executeTradeSelection } = useTradeExecution(
    tradeOffer, initData, 'aspect', selectedAspect?.id ?? null,
  );

  // Deep-link: auto-open the modal for `pendingOpenAspectId` once data loads.
  useAutoOpenItem(aspects, pendingOpenAspectId ?? null, openModal, loading);

  // ── Burn ──
  const handleBurnClick = useCallback(() => {
    if (!selectedAspect) return;
    setShowBurnDialog(true);
  }, [selectedAspect]);

  const handleBurnConfirm = useCallback(async () => {
    if (!selectedAspect || !chatId) return;
    setBurnProcessing(true);
    try {
      const result = await ApiService.burnAspect(selectedAspect.id, currentUserId, chatId, initData);
      burnResultRef.current = result.message || 'Aspect burned!';
      onSpinsUpdate?.(result.new_spin_total);
      setShowBurnDialog(false);
      setIsBurning(true);
      setTriggerBurn(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Burn failed';
      TelegramUtils.showAlert(msg);
    } finally {
      setBurnProcessing(false);
    }
  }, [selectedAspect, chatId, currentUserId, initData, onSpinsUpdate]);

  const handleBurnComplete = useCallback(() => {
    if (!selectedAspect) return;
    setTriggerBurn(false);
    setIsBurning(false);
    removeAspect(selectedAspect.id);
    onAspectRemove?.(selectedAspect.id);
    closeModal();
    TelegramUtils.showAlert(burnResultRef.current);
  }, [closeModal, selectedAspect, removeAspect, onAspectRemove]);

  const handleBurnCancel = useCallback(() => setShowBurnDialog(false), []);

  // ── Lock / Unlock ──
  const handleLockClick = useCallback(() => {
    if (!selectedAspect) return;
    setShowLockDialog(true);
  }, [selectedAspect]);

  const handleLockConfirm = useCallback(async () => {
    if (!selectedAspect || !chatId) return;
    setLockProcessing(true);
    try {
      const wantLock = !selectedAspect.locked;
      const result = await ApiService.lockAspect(selectedAspect.id, currentUserId, chatId, wantLock, initData);
      setClaimState({ balance: result.balance, loading: false });
      onClaimPointsUpdate?.(result.balance);

      updateSelectedAspect({ locked: result.locked });
      updateAspect(selectedAspect.id, { locked: result.locked });
      onAspectUpdate?.(selectedAspect.id, { locked: result.locked });

      TelegramUtils.showAlert(result.message || (result.locked ? 'Locked!' : 'Unlocked!'));
      setShowLockDialog(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Lock/unlock failed';
      TelegramUtils.showAlert(msg);
    } finally {
      setLockProcessing(false);
    }
  }, [selectedAspect, chatId, currentUserId, initData, updateAspect, onAspectUpdate, onClaimPointsUpdate]);

  const handleLockCancel = useCallback(() => setShowLockDialog(false), []);

  // ── Equip ──
  const handleEquipClick = useCallback(() => {
    if (!selectedAspect) return;
    setModalOpen(false);
    setShowEquipSelector(true);
  }, [selectedAspect, setModalOpen]);

  const handleEquipCardSelect = useCallback((card: CardData) => {
    setEquipSelectedCard(card);
    setShowEquipSelector(false);
    setShowEquipNameDialog(true);
  }, []);

  const handleEquipNameConfirm = useCallback(async (namePrefix: string) => {
    if (!selectedAspect || !equipSelectedCard || !chatId) return;
    setEquipProcessing(true);
    try {
      await ApiService.initiateEquip(
        selectedAspect.id,
        equipSelectedCard.id,
        currentUserId,
        chatId,
        initData,
        namePrefix,
      );
      TelegramUtils.closeApp();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to initiate equip';
      TelegramUtils.showAlert(msg);
      setEquipProcessing(false);
    }
  }, [selectedAspect, equipSelectedCard, chatId, currentUserId, initData]);

  const handleEquipNameCancel = useCallback(() => {
    setShowEquipNameDialog(false);
    setEquipSelectedCard(null);
  }, []);

  const handleEquipSelectorClose = useCallback(() => {
    setShowEquipSelector(false);
    if (selectedAspect) {
      setModalOpen(true);
    }
  }, [selectedAspect, setModalOpen]);

  // ── Share ──
  const handleShareAspect = useCallback(async (aspectId: number) => {
    try {
      await ApiService.shareAspect(aspectId, currentUserId, initData);
      TelegramUtils.showAlert('Shared to chat!');
    } catch (err) {
      console.error('Share aspect error:', err);
      const message = err instanceof Error ? err.message : 'Failed to share aspect.';
      TelegramUtils.showAlert(message);
    }
  }, [currentUserId, initData]);

  const shareEnabled = Boolean(initData) && !isTradeMode;

  // ── Trade initiation (from normal collection mode) ──
  const handleTradeClick = useCallback(() => {
    if (!selectedAspect || !isOwnCollection) return;
    closeModal();
    onTradeInitiate?.({ type: 'aspect', id: selectedAspect.id, title: selectedAspect.display_name, rarity: selectedAspect.rarity });
  }, [selectedAspect, isOwnCollection, closeModal, onTradeInitiate]);

  // Derive burn reward & lock cost from config
  const burnReward = selectedAspect && config
    ? config.burn_rewards[selectedAspect.rarity] ?? 0
    : 0;
  const lockCost = selectedAspect && config
    ? config.lock_costs[selectedAspect.rarity] ?? 0
    : 0;

  const lockDialogCard: CardData | null = selectedAspect
    ? {
        id: selectedAspect.id,
        base_name: selectedAspect.display_name,
        modifier: null,
        rarity: selectedAspect.rarity,
        locked: selectedAspect.locked,
      }
    : null;

  // Action buttons
  const actionButtons = useMemo<ActionButton[]>(() => {
    if (loading || error || !selectedAspect || !showModal) return [];

    // Trade mode: show Select button for other users' aspects
    if (isTradeMode && selectedAspect.user_id !== currentUserId) {
      return [{
        id: 'select',
        text: tradeExecuting ? 'Loading...' : 'Select',
        onClick: executeTradeSelection,
        variant: 'trade-blue' as const,
        disabled: tradeExecuting,
      }];
    }

    if (isReadOnly || isTradeMode || !isOwnCollection) return [];

    const buttons: ActionButton[] = [];

    buttons.push({
      id: 'lock',
      text: selectedAspect.locked ? 'Unlock' : 'Lock',
      onClick: handleLockClick,
      variant: 'lock-grey',
    });

    buttons.push({
      id: 'equip',
      text: 'Equip',
      onClick: handleEquipClick,
      variant: 'equip-green',
    });

    buttons.push({
      id: 'trade',
      text: 'Trade',
      onClick: handleTradeClick,
      variant: 'trade-blue',
    });

    buttons.push({
      id: 'burn',
      text: 'Burn',
      onClick: handleBurnClick,
      variant: 'burn-red',
    });

    return buttons;
  }, [
    loading, error, selectedAspect, showModal, isTradeMode, isReadOnly, isOwnCollection, currentUserId, tradeExecuting,
    handleLockClick, handleEquipClick, handleTradeClick, handleBurnClick, executeTradeSelection,
  ]);

  const isActionPanelVisible = actionButtons.length > 0;

  if (loading) {
    return <Loading message={isTradeMode ? 'Loading trade options...' : 'Loading aspects...'} />;
  }

  if (error) {
    return (
      <div className="error-container">
        <h2>Error</h2>
        <p>{error}</p>
        <button onClick={() => { void (isTradeMode ? refetchTradeAspects() : refetch()); }}>Retry</button>
      </div>
    );
  }

  return (
    <>
      <div className={`collection-tab-content ${isActionPanelVisible ? 'with-action-panel' : ''}`}>
        <div className="app-content">
          {isTradeMode && tradeOffer && (
            <TradeHeader title={tradeOffer.title} rarity={tradeOffer.rarity} />
          )}
          {aspects.length > 0 && (
            <FilterSortControls
              filterOptions={filterOptions}
              sortOptions={sortOptions}
              onFilterChange={onFilterChange}
              onSortChange={onSortChange}
              showOwnerFilter={isReadOnly || isTradeMode}
              showCharacterFilter={false}
              showAspectStatusFilter={false}
              filterValues={filterValues}
              counter={{
                current: displayedAspects.length,
                total: aspects.length,
              }}
            />
          )}

          {aspects.length === 0 ? (
            <div className="no-cards-container">
              <h2>{isTradeMode ? 'No trade options' : 'No aspects yet'}</h2>
              <p>{isTradeMode
                ? 'No aspects are available to trade for in this chat.'
                : isOwnCollection
                  ? "You don't own any aspects yet."
                  : `${collectionOwnerLabel} doesn't own any aspects yet.`}</p>
            </div>
          ) : displayedAspects.length === 0 ? (
            <div className="no-cards-container">
              <h2>No aspects match your filters</h2>
              <p>Try adjusting your filter settings.</p>
            </div>
          ) : (
            <AspectGrid
              aspects={displayedAspects}
              onAspectClick={openModal}
              initData={initData}
              onRefresh={isTradeMode ? refetchTradeAspects : (onRefreshProp ?? (!isReadOnly ? refetch : undefined))}
              scrollToItemId={pendingOpenAspectId ?? null}
            />
          )}
        </div>
      </div>

      {/* Aspect detail modal */}
      {selectedAspect && (
        <AspectModal
          isOpen={showModal}
          aspect={selectedAspect}
          initData={initData}
          onClose={closeModal}
          isActionPanelVisible={isActionPanelVisible}
          orientation={orientation}
          orientationKey={orientationKey}
          triggerBurn={triggerBurn}
          onBurnComplete={handleBurnComplete}
          isBurning={isBurning}
          onShare={shareEnabled ? handleShareAspect : undefined}
        />
      )}

      {/* Burn confirmation */}
      <BurnConfirmDialog
        isOpen={showBurnDialog}
        onConfirm={() => void handleBurnConfirm()}
        onCancel={handleBurnCancel}
        cardName={selectedAspect?.display_name}
        spinReward={burnReward}
        processing={burnProcessing}
      />

      {/* Lock confirmation */}
      <LockConfirmDialog
        isOpen={showLockDialog}
        locking={lockProcessing}
        card={lockDialogCard}
        lockCost={lockCost}
        claimState={claimState}
        onConfirm={() => void handleLockConfirm()}
        onCancel={handleLockCancel}
      />

      {/* Action panel */}
      <ActionPanel
        buttons={actionButtons}
        visible={isActionPanelVisible}
      />

      {/* Equip card selector */}
      {selectedAspect && chatId && (
        <EquipCardSelector
          isOpen={showEquipSelector}
          aspect={selectedAspect}
          currentUserId={currentUserId}
          chatId={chatId}
          initData={initData}
          onCardSelect={handleEquipCardSelect}
          onClose={handleEquipSelectorClose}
        />
      )}

      {/* Equip name dialog */}
      {selectedAspect && equipSelectedCard && (
        <EquipNameDialog
          isOpen={showEquipNameDialog}
          aspect={selectedAspect}
          card={equipSelectedCard}
          onConfirm={(name) => void handleEquipNameConfirm(name)}
          onCancel={handleEquipNameCancel}
          processing={equipProcessing}
        />
      )}
    </>
  );
};

export default AspectsView;
