import AllCards from './AllCards';
import FilterSortControls from './FilterSortControls';
import { Title } from '@/components/common';
import { ProfileView } from '@/components/profile';
import type { CardData, View, ProfileState } from '@/types';
import type { FilterOptions, SortOptions } from './FilterSortControls';

interface TabsProps {
  onCurrentTabClick: () => void;
  onAllTabClick: () => void;
  onProfileTabClick: () => void;
}

interface CurrentViewProps {
  cards: CardData[];
  filteredCards: CardData[];
  initData: string | null;
  onOpenModal: (card: CardData) => void;
  currentGridFilterOptions: FilterOptions;
  currentGridSortOptions: SortOptions;
  onCurrentGridFilterChange: (filters: FilterOptions) => void;
  onCurrentGridSortChange: (sort: SortOptions) => void;
  collectionOwnerLabel: string;
  isOwnCollection: boolean;
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
  tabs,
  currentView,
  allView,
  profileView
}: CardViewProps) => {
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
        <Title
          title={view === 'all'
            ? isTradeView && tradeCardName
              ? `Trade for ${tradeCardName}`
              : 'All cards'
            : `${collectionOwnerLabel}'s collection`}
        />

        {view === 'current' && (
          currentView.cards.length > 0 ? (
            <>
              <FilterSortControls
                cards={currentView.cards}
                filterOptions={currentView.currentGridFilterOptions}
                sortOptions={currentView.currentGridSortOptions}
                onFilterChange={currentView.onCurrentGridFilterChange}
                onSortChange={currentView.onCurrentGridSortChange}
                showOwnerFilter={false}
                counter={{
                  current: currentView.filteredCards.length,
                  total: currentView.cards.length
                }}
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
            <p>
              {currentView.isOwnCollection
                ? "You don't own any cards yet."
                : `${currentView.collectionOwnerLabel} doesn't own any cards yet.`}
            </p>
          )
        )}

        {view === 'all' && (
          allView.loading ? (
            <Title title="Loading..." loading />
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
                counter={{
                  current: allView.displayedCards.length,
                  total: allView.baseCards.length
                }}
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
