import Card from './Card';
import AllCards from './AllCards';
import FilterSortControls from './FilterSortControls';
import AppLoading from './AppLoading';
import type { CardData, View, OrientationData } from '../types';
import type { FilterOptions, SortOptions } from './FilterSortControls';

interface TabsProps {
  onCurrentTabClick: () => void;
  onAllTabClick: () => void;
}

interface CurrentViewProps {
  cards: CardData[];
  filteredCards: CardData[];
  isGridView: boolean;
  isActionPanelVisible: boolean;
  shareEnabled: boolean;
  orientation: OrientationData;
  orientationKey: number;
  initData: string | null;
  onGridToggle: () => void;
  onCardOpen: (card: Pick<CardData, 'id' | 'chat_id'>) => void;
  onOpenModal: (card: CardData) => void;
  onShare?: (cardId: number) => Promise<void> | void;
  currentGridFilterOptions: FilterOptions;
  currentGridSortOptions: SortOptions;
  onCurrentGridFilterChange: (filters: FilterOptions) => void;
  onCurrentGridSortChange: (sort: SortOptions) => void;
  collectionOwnerLabel: string;
  isOwnCollection: boolean;
  triggerBurn?: boolean;
  onBurnComplete?: () => void;
}

interface AllViewProps {
  baseCards: CardData[];
  displayedCards: CardData[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  filterOptions: FilterOptions;
  sortOptions: SortOptions;
  onFilterChange: (filters: FilterOptions) => void;
  onSortChange: (sort: SortOptions) => void;
  initData: string | null;
  onOpenModal: (card: CardData) => void;
}

interface CardViewProps {
  view: View;
  hasChatScope: boolean;
  isTradeGridActive: boolean;
  isTradeView: boolean;
  tradeCardName: string | null;
  collectionOwnerLabel: string;
  currentIndex: number;
  tabs: TabsProps;
  currentView: CurrentViewProps;
  allView: AllViewProps;
}

const CardView = ({
  view,
  hasChatScope,
  isTradeGridActive,
  isTradeView,
  tradeCardName,
  collectionOwnerLabel,
  currentIndex,
  tabs,
  currentView,
  allView
}: CardViewProps) => {
  const currentCard = currentView.cards[currentIndex];

  return (
    <>
      <div className="tabs">
        <button
          className={`tab ${view === 'current' ? 'active' : ''}`}
          onClick={tabs.onCurrentTabClick}
        >
          Current
        </button>
        {hasChatScope && (
          <button
            className={`tab ${view === 'all' && !isTradeGridActive ? 'active' : ''}`}
            onClick={tabs.onAllTabClick}
          >
            All
          </button>
        )}
      </div>

      <div className="app-content">
        <div className="title-container">
          {view === 'current' && currentView.cards.length > 0 && !currentView.isGridView && (
            <div className="card-position-indicator">
              <span className="position-current">{currentIndex + 1}</span>
              <span className="position-separator"> / </span>
              <span className="position-total">{currentView.cards.length}</span>
            </div>
          )}
          {view === 'current' && currentView.cards.length > 0 && (
            <button
              className="view-toggle-button"
              onClick={currentView.onGridToggle}
              onTouchStart={(e) => e.stopPropagation()}
              onTouchEnd={(e) => e.stopPropagation()}
              aria-label={currentView.isGridView ? 'Currently in grid view' : 'Currently in gallery view'}
            >
              {currentView.isGridView ? 'Grid' : 'Gallery'}
            </button>
          )}
          <h1 className="app-title">
            {view === 'all'
              ? isTradeView && tradeCardName
                ? `Trade for ${tradeCardName}`
                : 'All cards'
              : `${collectionOwnerLabel}'s collection`}
          </h1>
        </div>

        {view === 'current' && (
          currentView.cards.length > 0 ? (
            currentView.isGridView ? (
              <>
                <FilterSortControls
                  cards={currentView.cards}
                  filterOptions={currentView.currentGridFilterOptions}
                  sortOptions={currentView.currentGridSortOptions}
                  onFilterChange={currentView.onCurrentGridFilterChange}
                  onSortChange={currentView.onCurrentGridSortChange}
                  showOwnerFilter={false}
                />
                {currentView.filteredCards.length === 0 ? (
                  <div className="no-cards-container">
                    <h2>No cards match your filter</h2>
                    <p>Try selecting a different rarity or clearing the filter.</p>
                  </div>
                ) : (
                  <AllCards
                    cards={currentView.filteredCards}
                    onCardClick={currentView.onOpenModal}
                    initData={currentView.initData}
                  />
                )}
              </>
            ) : (
              <div className={`card-container ${currentView.isActionPanelVisible ? 'with-action-panel' : ''}`}>
                {currentCard ? (
                  <Card
                    {...currentCard}
                    orientation={currentView.orientation}
                    tiltKey={currentView.orientationKey}
                    initData={currentView.initData}
                    shiny={true}
                    onShare={currentView.shareEnabled ? currentView.onShare : undefined}
                    showShareButton={currentView.shareEnabled}
                    onCardOpen={currentView.onCardOpen}
                    triggerBurn={currentView.triggerBurn}
                    onBurnComplete={currentView.onBurnComplete}
                  />
                ) : (
                  <p>No card selected.</p>
                )}
              </div>
            )
          ) : (
            <p>
              {currentView.isOwnCollection
                ? "You don't own any cards yet."
                : `${currentView.collectionOwnerLabel} doesn't own any cards yet.`}
            </p>
          )
        )}

        {view === 'all' && (
          allView.loading ? (
            <AppLoading />
          ) : allView.error ? (
            <div className="error-container">
              <h2>{isTradeView ? 'Error loading trade options' : 'Error loading cards'}</h2>
              <p>{allView.error}</p>
              <button onClick={allView.onRetry}>Retry</button>
            </div>
          ) : allView.baseCards.length === 0 ? (
            <div className="no-cards-container">
              <h2>{isTradeView ? 'No trade options' : 'No cards found'}</h2>
              <p>
                {isTradeView
                  ? 'No other cards are available in this chat right now.'
                  : 'There are no cards in the system yet.'}
              </p>
            </div>
          ) : (
            <>
              <FilterSortControls
                cards={allView.baseCards}
                filterOptions={allView.filterOptions}
                sortOptions={allView.sortOptions}
                onFilterChange={allView.onFilterChange}
                onSortChange={allView.onSortChange}
              />
              {allView.displayedCards.length === 0 ? (
                <div className="no-cards-container">
                  <h2>No cards match your filters</h2>
                  <p>Try adjusting your filter settings to see more cards.</p>
                </div>
              ) : (
                <AllCards
                  cards={allView.displayedCards}
                  onCardClick={allView.onOpenModal}
                  initData={allView.initData}
                />
              )}
            </>
          )
        )}
      </div>
    </>
  );
};

export default CardView;
