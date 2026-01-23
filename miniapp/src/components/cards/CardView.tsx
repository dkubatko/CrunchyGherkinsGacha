import Card from './Card';
import AllCards from './AllCards';
import FilterSortControls from './FilterSortControls';
import { AppLoading } from '@/components/common';
import { ProfileView } from '@/components/profile';
import type { CardData, View, OrientationData, ProfileState } from '@/types';
import type { FilterOptions, SortOptions } from './FilterSortControls';

interface TabsProps {
  onCurrentTabClick: () => void;
  onAllTabClick: () => void;
  onProfileTabClick: () => void;
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
  isBurning?: boolean;
}

interface AllViewProps {
  baseCards: CardData[];
  displayedCards: CardData[];
  loading: boolean;
  error: string | null;
  onRetry: () => Promise<void>;
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
  profileView: ProfileState;
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
  allView,
  profileView
}: CardViewProps) => {
  const currentCard = currentView.cards[currentIndex];

  return (
    <>
      <div className="tabs">
        {profileView.profile && (
          <button
            className={`tab ${view === 'profile' ? 'active' : ''}`}
            onClick={tabs.onProfileTabClick}
            disabled={currentView.isBurning}
          >
            Profile
          </button>
        )}
        <button
          className={`tab ${view === 'current' ? 'active' : ''}`}
          onClick={tabs.onCurrentTabClick}
          disabled={currentView.isBurning}
        >
          Current
        </button>
        {hasChatScope && (
          <button
            className={`tab ${view === 'all' && !isTradeGridActive ? 'active' : ''}`}
            onClick={tabs.onAllTabClick}
            disabled={currentView.isBurning}
          >
            All
          </button>
        )}
      </div>

      <div className="app-content">
        {view === 'profile' ? (
          <ProfileView 
            profile={profileView.profile} 
            cards={currentView.cards}
            loading={profileView.loading} 
            error={profileView.error} 
          />
        ) : (
          <>
        <div className="title-container">
          {view === 'current' && currentView.cards.length > 0 && (
            <div className="card-position-indicator">
              <span className="position-current">
                {currentView.isGridView ? currentView.filteredCards.length : currentIndex + 1}
              </span>
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
              disabled={currentView.isBurning}
              aria-label={currentView.isGridView ? 'Currently in grid view' : 'Currently in gallery view'}
            >
              {currentView.isGridView ? 'Grid' : 'Gallery'}
            </button>
          )}
          {view === 'all' && allView.baseCards.length > 0 && !allView.loading && !allView.error && (
            <div className="card-position-indicator">
              <span className="position-current">{allView.displayedCards.length}</span>
              <span className="position-separator"> / </span>
              <span className="position-total">{allView.baseCards.length}</span>
            </div>
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
            <AppLoading title="Loading..." />
          ) : allView.error ? (
            <div className="error-container">
              <h2>{isTradeView ? 'Error loading trade options' : 'Error loading cards'}</h2>
              <p>{allView.error}</p>
              <button onClick={() => { void allView.onRetry(); }}>Retry</button>
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
          </>
        )}
      </div>
    </>
  );
};

export default CardView;
