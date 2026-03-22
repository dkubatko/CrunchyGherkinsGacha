import { useState, useCallback, useMemo, useEffect } from 'react';
import './AspectsTab.css';

// Components
import { AspectGrid, AspectModal } from '@/components/aspects';
import { ActionPanel, Title } from '@/components/common';
import Loading from '@/components/common/Loading';
import { BurnConfirmDialog, LockConfirmDialog } from '@/components/dialogs';
import type { ActionButton } from '@/components/common';

// Hooks
import { useAspects } from '@/hooks/useAspects';
import { useAspectFiltering } from '@/hooks/useAspectFiltering';

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
}

const AspectsTab = ({ currentUserId, chatId, initData }: AspectsTabProps) => {
  const { aspects, loading, error, refetch } = useAspects(initData, chatId);

  // Filtering / sorting
  const {
    displayedAspects,
    filterOptions,
    sortOptions,
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
    if (selectedAspect.locked) {
      TelegramUtils.showAlert('Unlock this aspect before burning it.');
      return;
    }
    setShowBurnDialog(true);
  }, [selectedAspect]);

  const handleBurnConfirm = useCallback(async () => {
    if (!selectedAspect || !chatId) return;
    setBurnProcessing(true);
    try {
      const result = await ApiService.burnAspect(selectedAspect.id, currentUserId, chatId, initData);
      TelegramUtils.showAlert(result.message || 'Aspect burned!');
      closeModal();
      setShowBurnDialog(false);
      await refetch();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Burn failed';
      TelegramUtils.showAlert(msg);
    } finally {
      setBurnProcessing(false);
    }
  }, [selectedAspect, chatId, currentUserId, initData, closeModal, refetch]);

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

  // Action buttons when a modal is open
  const actionButtons = useMemo<ActionButton[]>(() => {
    if (!selectedAspect || !showModal) return [];
    const buttons: ActionButton[] = [];

    buttons.push({
      id: 'lock',
      text: selectedAspect.locked ? '🔓 Unlock' : '🔒 Lock',
      onClick: handleLockClick,
      variant: 'secondary',
    });

    if (!selectedAspect.locked) {
      buttons.push({
        id: 'burn',
        text: '🔥 Burn',
        onClick: handleBurnClick,
        variant: 'burn-red',
      });
    }

    return buttons;
  }, [selectedAspect, showModal, handleLockClick, handleBurnClick]);

  const isActionPanelVisible = actionButtons.length > 0;

  // Unique set names for filter dropdown
  const setNames = useMemo(() => {
    const names = new Set<string>();
    aspects.forEach((a) => {
      if (a.aspect_definition?.set_name) names.add(a.aspect_definition.set_name);
    });
    return Array.from(names).sort();
  }, [aspects]);

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
          <Title title="Aspects" />

          {/* Filter / sort controls */}
          {aspects.length > 0 && (
            <div className="aspect-filter-controls">
              <div className="aspect-filter-row">
                <select
                  value={filterOptions.rarity}
                  onChange={(e) => onFilterChange({ ...filterOptions, rarity: e.target.value })}
                  className="aspect-filter-select"
                >
                  <option value="">All Rarities</option>
                  {['Common', 'Rare', 'Epic', 'Legendary', 'Unique'].map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>

                <select
                  value={filterOptions.locked}
                  onChange={(e) => onFilterChange({ ...filterOptions, locked: e.target.value })}
                  className="aspect-filter-select"
                >
                  <option value="">Lock Status</option>
                  <option value="locked">Locked</option>
                  <option value="unlocked">Unlocked</option>
                </select>

                {setNames.length > 1 && (
                  <select
                    value={filterOptions.setName}
                    onChange={(e) => onFilterChange({ ...filterOptions, setName: e.target.value })}
                    className="aspect-filter-select"
                  >
                    <option value="">All Sets</option>
                    {setNames.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                )}

                <select
                  value={`${sortOptions.field}-${sortOptions.direction}`}
                  onChange={(e) => {
                    const [field, direction] = e.target.value.split('-') as [typeof sortOptions.field, typeof sortOptions.direction];
                    onSortChange({ field, direction });
                  }}
                  className="aspect-filter-select"
                >
                  <option value="rarity-desc">Rarity ↓</option>
                  <option value="rarity-asc">Rarity ↑</option>
                  <option value="name-asc">Name A-Z</option>
                  <option value="name-desc">Name Z-A</option>
                  <option value="id-desc">Newest</option>
                  <option value="id-asc">Oldest</option>
                </select>
              </div>

              <div className="aspect-filter-count">
                {displayedAspects.length} / {aspects.length}
              </div>
            </div>
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
    </>
  );
};

export default AspectsTab;
