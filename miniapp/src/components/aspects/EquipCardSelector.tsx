import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { CardGrid, CardModal, FilterSortControls } from '@/components/cards';
import { ActionPanel, Title } from '@/components/common';
import type { ActionButton } from '@/components/common';
import Loading from '@/components/common/Loading';
import { useModal, useOrientation, useCardFiltering } from '@/hooks';
import { ApiService } from '@/services/api';
import { TelegramUtils } from '@/utils/telegram';
import type { AspectData, CardData } from '@/types';
import './EquipCardSelector.css';

interface EquipCardSelectorProps {
  isOpen: boolean;
  aspect: AspectData;
  currentUserId: number;
  chatId: string;
  initData: string;
  onCardSelect: (card: CardData) => void;
  onClose: () => void;
}

const EquipCardSelector = ({
  isOpen,
  aspect,
  currentUserId,
  chatId,
  initData,
  onCardSelect,
  onClose,
}: EquipCardSelectorProps) => {
  const [cards, setCards] = useState<CardData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { showModal, modalCard, openModal, closeModal } = useModal();
  const { orientation, orientationKey } = useOrientation({ enabled: isOpen });
  const {
    displayedCards,
    filterOptions,
    sortOptions,
    onFilterChange,
    onSortChange,
  } = useCardFiltering(cards, { includeOwnerFilter: false });

  // Fetch eligible cards when opened
  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setError(null);

    ApiService.getEligibleCards(aspect.id, currentUserId, chatId, initData)
      .then((data) => {
        setCards(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to load cards');
        setLoading(false);
      });
  }, [isOpen, aspect.id, currentUserId, chatId, initData]);

  // Toggle body class so portal z-indexes stack above the selector
  useEffect(() => {
    if (isOpen) {
      document.body.classList.add('equip-selector-open');
    } else {
      document.body.classList.remove('equip-selector-open');
    }
    return () => document.body.classList.remove('equip-selector-open');
  }, [isOpen]);

  // Ref-based BackButton handler to avoid re-registering on every state change
  const handleBackRef = useRef(() => onClose());
  useEffect(() => {
    handleBackRef.current = () => {
      if (showModal) {
        closeModal();
      } else {
        onClose();
      }
    };
  }, [showModal, closeModal, onClose]);

  useEffect(() => {
    if (!isOpen) {
      TelegramUtils.hideBackButton();
      return;
    }
    const cleanup = TelegramUtils.setupBackButton(() => handleBackRef.current());
    return cleanup;
  }, [isOpen]);

  const handleCardClick = useCallback((card: CardData) => {
    TelegramUtils.triggerHapticImpact('light');
    openModal(card);
  }, [openModal]);

  const handleEquipClick = useCallback(() => {
    if (!modalCard) return;
    closeModal();
    onCardSelect(modalCard);
  }, [modalCard, closeModal, onCardSelect]);

  const actionButtons = useMemo<ActionButton[]>(() => {
    if (!modalCard) return [];
    return [{
      id: 'equip',
      text: 'Equip',
      onClick: handleEquipClick,
      variant: 'equip-green' as const,
    }];
  }, [modalCard, handleEquipClick]);

  const isActionPanelVisible = actionButtons.length > 0;

  if (!isOpen) return null;

  return (
    <div className="equip-card-selector">
      <div className={`equip-card-selector-content ${isActionPanelVisible ? 'with-action-panel' : ''}`}>
        <Title title={`Select a card for ${aspect.display_name}`} />

        {loading ? (
          <Loading message="Loading eligible cards..." />
        ) : error ? (
          <div className="no-cards-container">
            <h2>Error</h2>
            <p>{error}</p>
          </div>
        ) : cards.length === 0 ? (
          <div className="no-cards-container">
            <h2>No eligible cards</h2>
            <p>
              No cards match the requirements for this aspect.
              Cards must be unlocked, have fewer than 5 aspects, and have
              compatible rarity.
            </p>
          </div>
        ) : (
          <>
            <FilterSortControls
              cards={cards}
              filterOptions={filterOptions}
              sortOptions={sortOptions}
              onFilterChange={onFilterChange}
              onSortChange={onSortChange}
              showOwnerFilter={false}
              counter={{
                current: displayedCards.length,
                total: cards.length,
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
                onCardClick={handleCardClick}
                initData={initData}
              />
            )}
          </>
        )}
      </div>

      {modalCard && (
        <CardModal
          isOpen={showModal}
          card={modalCard}
          orientation={orientation}
          orientationKey={orientationKey}
          initData={initData}
          onClose={closeModal}
          isActionPanelVisible={isActionPanelVisible}
          enableDownload={false}
        />
      )}

      <ActionPanel
        buttons={actionButtons}
        visible={isActionPanelVisible}
      />
    </div>
  );
};

export default EquipCardSelector;
