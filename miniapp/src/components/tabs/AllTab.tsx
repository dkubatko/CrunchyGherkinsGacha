import { useState, useCallback } from 'react';

// Components
import { CardGrid, CardModal, FilterSortControls } from '@/components/cards';
import { AspectGrid, AspectModal } from '@/components/aspects';
import { SubTabToggle } from '@/components/common';
import Loading from '@/components/common/Loading';

// Hooks
import { useAllCards, useOrientation, useModal, useCardFiltering, useAllChatAspectsReadonly } from '@/hooks';
import { useAspectFiltering } from '@/hooks/useAspectFiltering';

// Services
import { ApiService } from '@/services/api';

// Utils
import { TelegramUtils } from '@/utils/telegram';

// Types
import type { AspectData } from '@/types';

interface AllTabProps {
  chatId: string;
  initData: string;
  currentUserId: number;
}

interface AllTabProps {
  chatId: string;
  initData: string;
}

type AllSubTab = 'cards' | 'aspects';

const SUB_TABS = [
  { key: 'cards', label: 'All Cards' },
  { key: 'aspects', label: 'All Aspects' },
];

const AllTab = ({ chatId, initData, currentUserId }: AllTabProps) => {
  // Sub-tab state
  const [activeSubTab, setActiveSubTab] = useState<AllSubTab>('cards');
  const [mountedSubTabs, setMountedSubTabs] = useState<Set<AllSubTab>>(new Set(['cards']));

  const handleSubTabChange = useCallback((key: string) => {
    const tab = key as AllSubTab;
    setActiveSubTab(tab);
    setMountedSubTabs(prev => {
      if (prev.has(tab)) return prev;
      const next = new Set(prev);
      next.add(tab);
      return next;
    });
  }, []);

  // Shared orientation
  const { orientation, orientationKey } = useOrientation({ enabled: true });

  // Cards data
  const { showModal: showCardModal, modalCard, openModal: openCardModal, closeModal: closeCardModal } = useModal();
  const {
    allCards,
    loading: cardsLoading,
    error: cardsError,
    refetch: refetchAllCards,
  } = useAllCards(initData, chatId, { enabled: true });
  const {
    filterOptions: cardFilterOptions,
    sortOptions: cardSortOptions,
    displayedCards,
    onFilterChange: onCardFilterChange,
    onSortChange: onCardSortChange,
  } = useCardFiltering(allCards);

  // Aspects data
  const {
    allAspects,
    loading: aspectsLoading,
    error: aspectsError,
    refetch: refetchAllAspects,
  } = useAllChatAspectsReadonly(initData, chatId, { enabled: mountedSubTabs.has('aspects') });

  const {
    displayedAspects,
    filterOptions: aspectFilterOptions,
    sortOptions: aspectSortOptions,
    filterValues: aspectFilterValues,
    onFilterChange: onAspectFilterChange,
    onSortChange: onAspectSortChange,
  } = useAspectFiltering(allAspects);

  // Aspect modal state (read-only)
  const [selectedAspect, setSelectedAspect] = useState<AspectData | null>(null);
  const [showAspectModal, setShowAspectModal] = useState(false);

  const openAspectModal = useCallback((aspect: AspectData) => {
    setSelectedAspect(aspect);
    setShowAspectModal(true);
  }, []);

  const closeAspectModal = useCallback(() => {
    setShowAspectModal(false);
    setSelectedAspect(null);
  }, []);

  const handleShareAspect = useCallback(async (aspectId: number) => {
    try {
      await ApiService.shareAspect(aspectId, currentUserId, initData);
      TelegramUtils.showAlert('Shared to chat!');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to share aspect.';
      TelegramUtils.showAlert(message);
    }
  }, [currentUserId, initData]);

  const handleShareCard = useCallback(async (cardId: number) => {
    try {
      await ApiService.shareCard(cardId, currentUserId, initData);
      TelegramUtils.showAlert('Shared to chat!');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to share card.';
      TelegramUtils.showAlert(message);
    }
  }, [currentUserId, initData]);

  return (
    <>
      {/* Cards sub-tab */}
      {mountedSubTabs.has('cards') && (
        <div style={{ display: activeSubTab === 'cards' ? 'contents' : 'none' }}>
          <div className="app-content">
            <SubTabToggle tabs={SUB_TABS} activeTab={activeSubTab} onChange={handleSubTabChange} />
            {cardsLoading ? (
              <Loading message="Loading all cards..." />
            ) : cardsError ? (
              <div className="error-container">
                <h2>Error loading cards</h2>
                <p>{cardsError}</p>
                <button onClick={() => { void refetchAllCards(); }}>Retry</button>
              </div>
            ) : allCards.length === 0 ? (
              <div className="no-cards-container">
                <h2>No cards found</h2>
                <p>There are no cards in the system yet.</p>
              </div>
            ) : (
              <>
                <FilterSortControls
                  cards={allCards}
                  filterOptions={cardFilterOptions}
                  sortOptions={cardSortOptions}
                  onFilterChange={onCardFilterChange}
                  onSortChange={onCardSortChange}
                  counter={{
                    current: displayedCards.length,
                    total: allCards.length,
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
                    onCardClick={openCardModal}
                    initData={initData}
                  />
                )}
              </>
            )}
          </div>

          {/* Read-only card modal */}
          {modalCard && (
            <CardModal
              isOpen={showCardModal}
              card={modalCard}
              orientation={orientation}
              orientationKey={orientationKey}
              initData={initData}
              onClose={closeCardModal}
              isActionPanelVisible={false}
              onShare={handleShareCard}
            />
          )}
        </div>
      )}

      {/* Aspects sub-tab */}
      {mountedSubTabs.has('aspects') && (
        <div style={{ display: activeSubTab === 'aspects' ? 'contents' : 'none' }}>
          <div className="app-content">
            <SubTabToggle tabs={SUB_TABS} activeTab={activeSubTab} onChange={handleSubTabChange} />
            {aspectsLoading ? (
              <Loading message="Loading all aspects..." />
            ) : aspectsError ? (
              <div className="error-container">
                <h2>Error loading aspects</h2>
                <p>{aspectsError}</p>
                <button onClick={() => { void refetchAllAspects(); }}>Retry</button>
              </div>
            ) : allAspects.length === 0 ? (
              <div className="no-cards-container">
                <h2>No aspects found</h2>
                <p>There are no aspects in this chat yet.</p>
              </div>
            ) : (
              <>
                <FilterSortControls
                  filterOptions={aspectFilterOptions}
                  sortOptions={aspectSortOptions}
                  onFilterChange={onAspectFilterChange}
                  onSortChange={onAspectSortChange}
                  showCharacterFilter={false}
                  showAspectStatusFilter={false}
                  filterValues={aspectFilterValues}
                  counter={{
                    current: displayedAspects.length,
                    total: allAspects.length,
                  }}
                />
                {displayedAspects.length === 0 ? (
                  <div className="no-cards-container">
                    <h2>No aspects match your filters</h2>
                    <p>Try adjusting your filter settings.</p>
                  </div>
                ) : (
                  <AspectGrid
                    aspects={displayedAspects}
                    onAspectClick={openAspectModal}
                    initData={initData}
                  />
                )}
              </>
            )}
          </div>

          {/* Read-only aspect modal */}
          {selectedAspect && (
            <AspectModal
              isOpen={showAspectModal}
              aspect={selectedAspect}
              orientation={orientation}
              orientationKey={orientationKey}
              initData={initData}
              onClose={closeAspectModal}
              onShare={handleShareAspect}
              isActionPanelVisible={false}
            />
          )}
        </div>
      )}
    </>
  );
};

export default AllTab;
