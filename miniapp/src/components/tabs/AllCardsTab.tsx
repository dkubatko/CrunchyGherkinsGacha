// Components
import { CardGrid, CardModal, FilterSortControls } from '@/components/cards';
import { Title } from '@/components/common';
import Loading from '@/components/common/Loading';

// Hooks
import { useAllCards, useOrientation, useModal, useCardFiltering } from '@/hooks';

interface AllCardsTabProps {
  chatId: string;
  initData: string;
}

const AllCardsTab = ({ chatId, initData }: AllCardsTabProps) => {
  const { orientation, orientationKey } = useOrientation({ enabled: true });
  const { showModal, modalCard, openModal, closeModal } = useModal();

  const {
    allCards,
    loading,
    error,
    refetch: refetchAllCards,
  } = useAllCards(initData, chatId, { enabled: true });

  const {
    filterOptions,
    sortOptions,
    displayedCards,
    onFilterChange,
    onSortChange
  } = useCardFiltering(allCards);

  if (loading) {
    return <Loading message="Loading all cards..." />;
  }

  if (error) {
    return (
      <div className="error-container">
        <h2>Error loading cards</h2>
        <p>{error}</p>
        <button onClick={() => { void refetchAllCards(); }}>Retry</button>
      </div>
    );
  }

  if (allCards.length === 0) {
    return (
      <div className="no-cards-container">
        <h2>No cards found</h2>
        <p>There are no cards in the system yet.</p>
      </div>
    );
  }

  return (
    <div className="app-content">
      <Title title="All cards" />
      <FilterSortControls
        cards={allCards}
        filterOptions={filterOptions}
        sortOptions={sortOptions}
        onFilterChange={onFilterChange}
        onSortChange={onSortChange}
        counter={{
          current: displayedCards.length,
          total: allCards.length
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

      {/* Read-only card modal */}
      {modalCard && (
        <CardModal
          isOpen={showModal}
          card={modalCard}
          orientation={orientation}
          orientationKey={orientationKey}
          initData={initData}
          onClose={closeModal}
          isActionPanelVisible={false}
        />
      )}
    </div>
  );
};

export default AllCardsTab;
