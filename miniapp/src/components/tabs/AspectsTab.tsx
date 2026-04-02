import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import './AspectsTab.css';

// Components
import { AspectGrid, AspectModal, EquipCardSelector } from '@/components/aspects';
import { FilterSortControls } from '@/components/cards';
import { ActionPanel, Title } from '@/components/common';
import Loading from '@/components/common/Loading';
import { BurnConfirmDialog, LockConfirmDialog, EquipNameDialog } from '@/components/dialogs';
import type { ActionButton } from '@/components/common';

// Hooks
import { useAspects, useAllChatAspects } from '@/hooks';
import { useAspectFiltering } from '@/hooks/useAspectFiltering';
import { useOrientation } from '@/hooks';

// Services
import { ApiService } from '@/services/api';

// Utils
import { TelegramUtils } from '@/utils/telegram';

// Types
import type { AspectData, AspectConfigResponse, ClaimBalanceState, CardData } from '@/types';

interface AspectsTabProps {
  currentUserId: number;
  chatId: string | null;
  initData: string;
  targetUserId?: number;
  ownerLabel: string | null;
  subTabToggle?: React.ReactNode;
}

const AspectsTab = ({ currentUserId, chatId, initData, targetUserId, ownerLabel, subTabToggle }: AspectsTabProps) => {
  const { aspects, loading, error, refetch } = useAspects(initData, chatId, targetUserId);
  const { orientation, orientationKey } = useOrientation({ enabled: true });
  const isOwnCollection = !targetUserId || targetUserId === currentUserId;

  // Trade state
  const [selectedAspectForTrade, setSelectedAspectForTrade] = useState<AspectData | null>(null);
  const [isTradeView, setIsTradeView] = useState(false);
  const isTradeMode = Boolean(selectedAspectForTrade);

  // Fetch all other users' tradeable aspects when in trade mode
  const {
    allAspects: tradeAspects,
    loading: tradeAspectsLoading,
  } = useAllChatAspects(initData, selectedAspectForTrade?.id ?? null, {
    enabled: isTradeMode,
  });

  // Filtering / sorting
  const {
    displayedAspects,
    filterOptions,
    sortOptions,
    filterValues,
    onFilterChange,
    onSortChange,
  } = useAspectFiltering(aspects);

  // Modal state
  const [selectedAspect, setSelectedAspect] = useState<AspectData | null>(null);
  const [showModal, setShowModal] = useState(false);

  // Config (burn rewards + lock costs)
  const [config, setConfig] = useState<AspectConfigResponse | null>(null);

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

  // Load aspect config once
  useEffect(() => {
    if (!initData) return;
    ApiService.fetchAspectConfig(initData)
      .then(setConfig)
      .catch((err) => console.error('Failed to load aspect config:', err));
  }, [initData]);

  // Open / close modal
  const openModal = useCallback((aspect: AspectData) => {
    setSelectedAspect(aspect);
    setShowModal(true);
  }, []);

  const closeModal = useCallback(() => {
    setShowModal(false);
    setSelectedAspect(null);
  }, []);

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
      setShowBurnDialog(false);
      setIsBurning(true);
      setTriggerBurn(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Burn failed';
      TelegramUtils.showAlert(msg);
    } finally {
      setBurnProcessing(false);
    }
  }, [selectedAspect, chatId, currentUserId, initData]);

  const handleBurnComplete = useCallback(() => {
    setTriggerBurn(false);
    setIsBurning(false);
    closeModal();
    TelegramUtils.showAlert(burnResultRef.current);
    void refetch();
  }, [closeModal, refetch]);

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

      // Optimistically update the selected aspect
      setSelectedAspect((prev) => prev ? { ...prev, locked: result.locked } : prev);

      TelegramUtils.showAlert(result.message || (result.locked ? 'Locked!' : 'Unlocked!'));
      setShowLockDialog(false);
      await refetch();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Lock/unlock failed';
      TelegramUtils.showAlert(msg);
    } finally {
      setLockProcessing(false);
    }
  }, [selectedAspect, chatId, currentUserId, initData, refetch]);

  const handleLockCancel = useCallback(() => setShowLockDialog(false), []);

  // ── Equip ──
  const handleEquipClick = useCallback(() => {
    if (!selectedAspect) return;
    setShowModal(false);
    setShowEquipSelector(true);
  }, [selectedAspect]);

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
    // Re-open the aspect modal
    if (selectedAspect) {
      setShowModal(true);
    }
  }, [selectedAspect]);

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

  const shareEnabled = Boolean(initData);

  // ── Trade ──
  const switchToNormalView = useCallback(() => {
    setSelectedAspectForTrade(null);
    setIsTradeView(false);
    closeModal();
    TelegramUtils.hideBackButton();
  }, [closeModal]);

  const switchToNormalViewRef = useRef(switchToNormalView);
  useEffect(() => {
    switchToNormalViewRef.current = switchToNormalView;
  }, [switchToNormalView]);

  useEffect(() => {
    if (!isTradeView) {
      TelegramUtils.hideBackButton();
      return;
    }
    const cleanup = TelegramUtils.setupBackButton(() => {
      switchToNormalViewRef.current();
    });
    return cleanup;
  }, [isTradeView]);

  const handleTradeClick = useCallback(() => {
    if (!selectedAspect || !isOwnCollection) return;
    if (selectedAspect.locked) {
      TelegramUtils.showAlert('Unlock this aspect before trading it.');
      return;
    }
    setSelectedAspectForTrade(selectedAspect);
    setIsTradeView(true);
    closeModal();
  }, [selectedAspect, isOwnCollection, closeModal]);

  const handleSelectClick = useCallback(() => {
    if (!selectedAspectForTrade || !selectedAspect) return;
    const executeAspectTrade = async () => {
      try {
        await ApiService.executeAspectTrade(selectedAspectForTrade.id, selectedAspect.id, initData);
        TelegramUtils.closeApp();
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Trade request failed';
        TelegramUtils.showAlert(msg);
      }
    };
    executeAspectTrade();
    switchToNormalView();
  }, [selectedAspectForTrade, selectedAspect, initData, switchToNormalView]);

  // Derive burn reward & lock cost from config
  const burnReward = selectedAspect && config
    ? config.burn_rewards[selectedAspect.rarity] ?? 0
    : 0;
  const lockCost = selectedAspect && config
    ? config.lock_costs[selectedAspect.rarity] ?? 0
    : 0;

  // Build a CardData-shaped shim for LockConfirmDialog
  const lockDialogCard: CardData | null = selectedAspect
    ? {
        id: selectedAspect.id,
        base_name: selectedAspect.display_name,
        modifier: null,
        rarity: selectedAspect.rarity,
        locked: selectedAspect.locked,
      }
    : null;

  // Action buttons when a modal is open (only for own collection)
  const actionButtons = useMemo<ActionButton[]>(() => {
    if (!selectedAspect || !showModal || !isOwnCollection) return [];
    const buttons: ActionButton[] = [];

    if (isTradeView && selectedAspect.user_id !== currentUserId) {
      // In trade view: only show Select button for other users' aspects
      buttons.push({
        id: 'select',
        text: 'Select',
        onClick: () => void handleSelectClick(),
        variant: 'trade-blue',
      });
      return buttons;
    }

    if (!isTradeView) {
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
    }

    return buttons;
  }, [selectedAspect, showModal, isOwnCollection, isTradeView, currentUserId, handleLockClick, handleEquipClick, handleTradeClick, handleBurnClick, handleSelectClick]);

  const isActionPanelVisible = actionButtons.length > 0;

  if (loading) {
    return <Loading message="Loading aspects..." />;
  }

  if (error) {
    return (
      <div className="error-container">
        <h2>Error</h2>
        <p>{error}</p>
        <button onClick={() => void refetch()}>Retry</button>
      </div>
    );
  }

  return (
    <>
      <div className={`collection-tab-content ${isActionPanelVisible ? 'with-action-panel' : ''}`}>
        <div className="app-content">
          {isTradeView && selectedAspectForTrade ? (
            <>
              <Title title={`Trade for ${selectedAspectForTrade.display_name}`} />
              {tradeAspectsLoading ? (
                <Loading message="Loading aspects..." />
              ) : tradeAspects.length === 0 ? (
                <div className="no-cards-container">
                  <h2>No tradeable aspects</h2>
                  <p>No other users have tradeable aspects in this chat.</p>
                </div>
              ) : (
                <AspectGrid
                  aspects={tradeAspects}
                  onAspectClick={openModal}
                  initData={initData}
                />
              )}
            </>
          ) : (
            <>
              {subTabToggle || <Title title={`${ownerLabel ? `${ownerLabel}'s` : ''} Aspects`} />}

              {aspects.length > 0 && (
                <FilterSortControls
                  filterOptions={filterOptions}
                  sortOptions={sortOptions}
                  onFilterChange={onFilterChange}
                  onSortChange={onSortChange}
                  showOwnerFilter={false}
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
                  <h2>No aspects yet</h2>
                  <p>Roll aspects in the chat to start collecting!</p>
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
                />
              )}
            </>
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
          onShare={shareEnabled && isOwnCollection ? handleShareAspect : undefined}
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

export default AspectsTab;
