import { useState, useCallback, useEffect, useRef } from 'react';
import './App.css';

// Components
import Card from './components/Card';
import SingleCardView from './components/SingleCardView';
import AllCards from './components/AllCards';
import CardModal from './components/CardModal';
import FilterSortControls from './components/FilterSortControls';
import ActionPanel from './components/ActionPanel';
import Slots from './components/Slots';
import type { FilterOptions, SortOptions } from './components/FilterSortControls';
import type { ActionButton } from './components/ActionPanel';

// Hooks
import {
  useCards,
  useAllCards,
  useOrientation,
  useModal,
  useSwipeHandlers,
  useSlots
} from './hooks';

// Utils
import { TelegramUtils } from './utils/telegram';

// Services
import { ApiService } from './services/api';

// Types
import type { CardData, View } from './types';

// Build info
import { BUILD_INFO } from './build-info';

function App() {
  // Log build info to console for debugging
  console.log('App build info:', BUILD_INFO);
  
  // Core data hooks
  const { cards, loading, error, userData, initData } = useCards();
  const { symbols: slotsSymbols, spins: slotsSpins, loading: slotsLoading, error: slotsError, refetchSpins } = useSlots(
    userData?.slotsView && userData.chatId ? userData.chatId : undefined,
    userData?.currentUserId
  );
  
  // UI state
  const [currentIndex, setCurrentIndex] = useState(0);
  const [view, setView] = useState<View>('current');
  const [selectedCardForTrade, setSelectedCardForTrade] = useState<CardData | null>(null);
  const [isTradeGridActive, setIsTradeGridActive] = useState(false);
  const [isGridView, setIsGridView] = useState(false);

  // Filter and sort state
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    owner: '',
    rarity: ''
  });
  const [sortOptions, setSortOptions] = useState<SortOptions>({
    field: 'rarity',
    direction: 'desc'
  });
  
  // Current view grid filter and sort state (only rarity filter, but full sort options)
  const [currentGridFilterOptions, setCurrentGridFilterOptions] = useState<FilterOptions>({
    owner: '', // Always empty for current view
    rarity: ''
  });
  const [currentGridSortOptions, setCurrentGridSortOptions] = useState<SortOptions>({
    field: 'rarity',
    direction: 'desc'
  });

  const hasChatScope = Boolean(userData?.chatId);
  const isTradeView = view === 'all' && isTradeGridActive;
  const activeTradeCardId = isTradeView && selectedCardForTrade ? selectedCardForTrade.id : null;
  const cardsScopeChatId = isTradeView && selectedCardForTrade?.chat_id
    ? selectedCardForTrade.chat_id
    : userData?.chatId ?? null;
  const shouldFetchAllCards = hasChatScope || activeTradeCardId !== null;

  const {
    allCards,
    loading: allCardsLoading,
    error: allCardsError,
    refetch: refetchAllCards
  } = useAllCards(initData, cardsScopeChatId, {
    enabled: shouldFetchAllCards,
    tradeCardId: activeTradeCardId
  });

  const tradeCardName = selectedCardForTrade
    ? `${selectedCardForTrade.modifier} ${selectedCardForTrade.base_name}`
    : null;

  // Filtering and sorting logic
  const applyFiltersAndSorting = (cards: CardData[]) => {
    let filtered = cards;

    // Apply owner filter
    if (filterOptions.owner) {
      filtered = filtered.filter(card => card.owner === filterOptions.owner);
    }

    // Apply rarity filter
    if (filterOptions.rarity) {
      filtered = filtered.filter(card => card.rarity === filterOptions.rarity);
    }

    // Apply sorting
    const sorted = [...filtered].sort((a, b) => {
      let aValue: string | number;
      let bValue: string | number;

      switch (sortOptions.field) {
        case 'rarity': {
          // Define rarity order: Common -> Rare -> Epic -> Legendary
          const rarityOrder = ['Common', 'Rare', 'Epic', 'Legendary'];
          const aIndex = rarityOrder.indexOf(a.rarity);
          const bIndex = rarityOrder.indexOf(b.rarity);
          // If rarity not found in order, put it at the end
          aValue = aIndex === -1 ? rarityOrder.length : aIndex;
          bValue = bIndex === -1 ? rarityOrder.length : bIndex;
          break;
        }
        case 'id':
          aValue = a.id;
          bValue = b.id;
          break;
        case 'name':
          aValue = `${a.modifier} ${a.base_name}`.toLowerCase();
          bValue = `${b.modifier} ${b.base_name}`.toLowerCase();
          break;
        default:
          aValue = a.id;
          bValue = b.id;
      }

      if (typeof aValue === 'string' && typeof bValue === 'string') {
        const comparison = aValue.localeCompare(bValue);
        return sortOptions.direction === 'asc' ? comparison : -comparison;
      } else if (typeof aValue === 'number' && typeof bValue === 'number') {
        const comparison = aValue - bValue;
        return sortOptions.direction === 'asc' ? comparison : -comparison;
      }

      return 0;
    });

    return sorted;
  };

  const baseDisplayedCards = isTradeView && selectedCardForTrade
    ? allCards.filter((card) => card.id !== selectedCardForTrade.id)
    : allCards;

  const displayedCards = applyFiltersAndSorting(baseDisplayedCards);

  // Apply filtering and sorting for current view grid
  const applyCurrentGridFiltersAndSorting = (cards: CardData[]) => {
    let filtered = cards;

    // Apply rarity filter
    if (currentGridFilterOptions.rarity) {
      filtered = filtered.filter(card => card.rarity === currentGridFilterOptions.rarity);
    }

    // Apply sorting
    const sorted = [...filtered].sort((a, b) => {
      let aValue: string | number;
      let bValue: string | number;

      switch (currentGridSortOptions.field) {
        case 'rarity': {
          // Define rarity order: Common -> Rare -> Epic -> Legendary
          const rarityOrder = ['Common', 'Rare', 'Epic', 'Legendary'];
          const aIndex = rarityOrder.indexOf(a.rarity);
          const bIndex = rarityOrder.indexOf(b.rarity);
          // If rarity not found in order, put it at the end
          aValue = aIndex === -1 ? rarityOrder.length : aIndex;
          bValue = bIndex === -1 ? rarityOrder.length : bIndex;
          break;
        }
        case 'id':
          aValue = a.id;
          bValue = b.id;
          break;
        case 'name':
          aValue = `${a.modifier} ${a.base_name}`.toLowerCase();
          bValue = `${b.modifier} ${b.base_name}`.toLowerCase();
          break;
        default:
          aValue = a.id;
          bValue = b.id;
      }

      if (typeof aValue === 'string' && typeof bValue === 'string') {
        const comparison = aValue.localeCompare(bValue);
        return currentGridSortOptions.direction === 'asc' ? comparison : -comparison;
      } else if (typeof aValue === 'number' && typeof bValue === 'number') {
        const comparison = aValue - bValue;
        return currentGridSortOptions.direction === 'asc' ? comparison : -comparison;
      }

      return 0;
    });

    return sorted;
  };

  const filteredCurrentCards = applyCurrentGridFiltersAndSorting(cards);

  const shareEnabled = Boolean(initData && userData);
  
  // Feature hooks
  const { orientation, orientationKey, resetTiltReference } = useOrientation();
  const { showModal, modalCard, openModal, closeModal } = useModal();
  // Hide trade/navigation buttons when in single card mode
  useEffect(() => {
    if (userData?.singleCardView) {
      TelegramUtils.hideBackButton();
    }
  }, [userData?.singleCardView]);

  const exitTradeView = useCallback(() => {
    setIsTradeGridActive(false);
    setSelectedCardForTrade(null);
    closeModal();
    setView('current');
    setFilterOptions({ owner: '', rarity: '' });
    setSortOptions({ field: 'rarity', direction: 'desc' });
    TelegramUtils.hideBackButton();
  }, [closeModal]);

  const exitTradeViewRef = useRef(exitTradeView);

  useEffect(() => {
    exitTradeViewRef.current = exitTradeView;
  }, [exitTradeView]);
  
  // Memoized callback functions to prevent infinite re-renders
  const handleTradeClick = useCallback(() => {
    // Handle trade button click in current view (only if trading is enabled)
    if (userData?.enableTrade) {
      // Use modal card if open (grid view case), otherwise use current index card (gallery view case)
      const tradeCard = modalCard || cards[currentIndex];
      
      if (!tradeCard) {
        return;
      }

      if (!tradeCard.chat_id) {
        TelegramUtils.showAlert('This card cannot be traded because it is not associated with a chat yet.');
        return;
      }

      // Close modal if it's open before starting trade
      if (modalCard) {
        closeModal();
      }

      setSelectedCardForTrade(tradeCard);
      setIsTradeGridActive(!hasChatScope);
      setView('all');
    }
  }, [cards, currentIndex, modalCard, userData?.enableTrade, hasChatScope, closeModal]);

  const handleSelectClick = useCallback(() => {
    // Handle select button click in modal
    if (selectedCardForTrade && modalCard) {
      // Execute the trade via API
      const executeTrade = async () => {
        try {
          const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com';
          const response = await fetch(`${apiBaseUrl}/trade/${selectedCardForTrade.id}/${modalCard.id}`, {
            method: 'POST',
            headers: {
              'Authorization': `tma ${initData}`
            }
          });

          if (response.ok) {
            // Close the WebApp after successful trade request
            TelegramUtils.closeApp();
          } else {
            const errorData = await response.json();
            TelegramUtils.showAlert(`Trade request failed: ${errorData.detail || 'Unknown error'}`);
          }
        } catch (error) {
          console.error('Trade API error:', error);
          TelegramUtils.showAlert('Trade request failed: Network error');
        }
      };

      executeTrade();
      
      // Reset trading state
      exitTradeView();
    }
  }, [selectedCardForTrade, modalCard, initData, exitTradeView]);

  const handleCurrentTabClick = useCallback(() => {
    exitTradeView();
    // Don't reset grid view state - preserve it
  }, [exitTradeView]);

  const handleAllTabClick = useCallback(() => {
    setIsTradeGridActive(false);
    setSelectedCardForTrade(null);
    setView('all');
    // Don't reset filters - preserve All view state
  }, []);

  const handleGridToggle = useCallback(() => {
    setIsGridView(!isGridView);
    // Don't reset filters - preserve them when switching between grid/gallery
  }, [isGridView]);  const handleFilterChange = useCallback((newFilters: FilterOptions) => {
    setFilterOptions(newFilters);
  }, []);

  const handleSortChange = useCallback((newSort: SortOptions) => {
    setSortOptions(newSort);
  }, []);

  const handleCurrentGridFilterChange = useCallback((newFilters: FilterOptions) => {
    setCurrentGridFilterOptions(newFilters);
  }, []);

  const handleCurrentGridSortChange = useCallback((newSort: SortOptions) => {
    setCurrentGridSortOptions(newSort);
  }, []);

  const handleShareCard = useCallback(async (cardId: number) => {
    if (!initData) {
      TelegramUtils.showAlert('Unable to share card: missing Telegram init data.');
      return;
    }
    if (!userData) {
      TelegramUtils.showAlert('Unable to share card: user data unavailable.');
      return;
    }

    try {
      await ApiService.shareCard(cardId, userData.currentUserId, initData);
      TelegramUtils.showAlert('Shared to chat!');
    } catch (err) {
      console.error('Share card error:', err);
      const message = err instanceof Error ? err.message : 'Failed to share card.';
      TelegramUtils.showAlert(message);
    }
  }, [initData, userData]);

  useEffect(() => {
    if (!isTradeView) {
      TelegramUtils.hideBackButton();
      return;
    }

    const cleanup = TelegramUtils.setupBackButton(() => {
      exitTradeViewRef.current();
    });

    return cleanup;
  }, [isTradeView]);
  
  // Action Panel logic (replaces useMainButton)
  const getActionButtons = (): ActionButton[] => {
    if (loading || error) {
      return [];
    }

    // Show Trade button in current view for own collection (only if trading is enabled)
    // Allow in gallery view always, or in grid view when a modal card is open
    if (userData?.isOwnCollection && userData.enableTrade && cards.length > 0 && view === 'current' && !selectedCardForTrade && (!isGridView || modalCard)) {
      return [{
        id: 'trade',
        text: 'Trade',
        onClick: handleTradeClick,
        variant: 'primary'
      }];
    }
    // Show Select button in modal when trading and viewing others' cards (only if trading is enabled)
    else if (userData?.enableTrade && selectedCardForTrade && modalCard && view === 'all' && modalCard.owner && modalCard.owner !== TelegramUtils.getCurrentUsername()) {
      return [{
        id: 'select',
        text: 'Select',
        onClick: handleSelectClick,
        variant: 'primary'
      }];
    }

    return [];
  };

  const actionButtons = getActionButtons();
  const isActionPanelVisible = actionButtons.length > 0;

  const collectionOwnerLabel = (() => {
    if (!userData) {
      return 'Collection';
    }
    if (userData.collectionDisplayName && userData.collectionDisplayName.trim().length > 0) {
      return userData.collectionDisplayName;
    }
    if (userData.collectionUsername && userData.collectionUsername.trim().length > 0) {
      return `@${userData.collectionUsername}`;
    }
    return 'Collection';
  })();
  
  // Event handlers
  const swipeHandlers = useSwipeHandlers({
    cardsLength: cards.length,
    currentIndex,
    onIndexChange: setCurrentIndex,
    onTiltReset: resetTiltReference
  });

  // Loading state
  if (loading || (userData?.slotsView && slotsLoading)) {
    return <div className="app-container"><h1>Loading...</h1></div>;
  }

  // Error state
  if (error || (userData?.slotsView && slotsError)) {
    const displayError = error || slotsError;
    return <div className="app-container"><h1>Error: {displayError}</h1></div>;
  }

  // Slots View
  if (userData?.slotsView && userData.chatId && initData) {
    return (
      <div className="app-container">
        <Slots
          symbols={slotsSymbols}
          spins={slotsSpins}
          userId={userData.currentUserId}
          chatId={userData.chatId}
          initData={initData}
          onSpinConsumed={refetchSpins}
        />
      </div>
    );
  }

  // Single Card View (no tabs, no navigation or trade UI)
  if (userData?.singleCardView && userData.singleCardId && initData) {
    return (
      <div className="app-container">
        <SingleCardView
          cardId={userData.singleCardId}
          initData={initData}
          orientation={orientation}
          orientationKey={orientationKey}
        />
      </div>
    );
  }

  return (
    <div className={`app-container ${isActionPanelVisible ? 'with-action-panel' : ''}`} {...(view === 'current' ? swipeHandlers : {})}>
      {/* Tab Navigation */}
      <div className="tabs">
        <button 
          className={`tab ${view === 'current' ? 'active' : ''}`} 
          onClick={handleCurrentTabClick}
        >
          Current
        </button>
        {hasChatScope && (
          <button 
            className={`tab ${view === 'all' && !isTradeGridActive ? 'active' : ''}`} 
            onClick={handleAllTabClick}
          >
            All
          </button>
        )}
      </div>

      <div className="app-content">
        <div className="title-container">
          {view === 'current' && cards.length > 0 && !isGridView && (
            <div className="card-position-indicator">
              <span className="position-current">{currentIndex + 1}</span>
              <span className="position-separator"> / </span>
              <span className="position-total">{cards.length}</span>
            </div>
          )}
          {view === 'current' && cards.length > 0 && (
            <button 
              className="view-toggle-button"
              onClick={handleGridToggle}
              onTouchStart={(e) => e.stopPropagation()}
              onTouchEnd={(e) => e.stopPropagation()}
              aria-label={isGridView ? "Currently in grid view" : "Currently in gallery view"}
            >
              {isGridView ? "Grid" : "Gallery"}
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
        
        {/* Current View */}
        {view === 'current' && (
          <>
            {cards.length > 0 ? (
              <>
                {isGridView ? (
                  <>
                    <FilterSortControls
                      cards={cards}
                      filterOptions={currentGridFilterOptions}
                      sortOptions={currentGridSortOptions}
                      onFilterChange={handleCurrentGridFilterChange}
                      onSortChange={handleCurrentGridSortChange}
                      showOwnerFilter={false}
                    />
                    {filteredCurrentCards.length === 0 ? (
                      <div className="no-cards-container">
                        <h2>No cards match your filter</h2>
                        <p>Try selecting a different rarity or clearing the filter.</p>
                      </div>
                    ) : (
                      <AllCards
                        cards={filteredCurrentCards}
                        onCardClick={openModal}
                        initData={initData}
                      />
                    )}
                  </>
                ) : (
                  <div className={`card-container ${isActionPanelVisible ? 'with-action-panel' : ''}`}>
                    {/* Current Card */}
                    <Card 
                      {...cards[currentIndex]} 
                      orientation={orientation}
                      tiltKey={orientationKey}
                      initData={initData}
                      shiny={true}
                      onShare={shareEnabled ? handleShareCard : undefined}
                      showShareButton={shareEnabled}
                    />
                  </div>
                )}
              </>
            ) : (
              <p>
                {userData?.isOwnCollection
                  ? "You don't own any cards yet."
                  : `${collectionOwnerLabel} doesn't own any cards yet.`}
              </p>
            )}
          </>
        )}

        {/* All Cards View */}
        {view === 'all' && (
          <>
            {allCardsLoading ? (
              <div className="loading-container">
                <h2>{isTradeView ? 'Loading trade options...' : 'Loading all cards...'}</h2>
              </div>
            ) : allCardsError ? (
              <div className="error-container">
                <h2>{isTradeView ? 'Error loading trade options' : 'Error loading cards'}</h2>
                <p>{allCardsError}</p>
                <button onClick={refetchAllCards}>Retry</button>
              </div>
            ) : baseDisplayedCards.length === 0 ? (
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
                  cards={baseDisplayedCards}
                  filterOptions={filterOptions}
                  sortOptions={sortOptions}
                  onFilterChange={handleFilterChange}
                  onSortChange={handleSortChange}
                />
                {displayedCards.length === 0 ? (
                  <div className="no-cards-container">
                    <h2>No cards match your filters</h2>
                    <p>Try adjusting your filter settings to see more cards.</p>
                  </div>
                ) : (
                  <AllCards
                    cards={displayedCards}
                    onCardClick={openModal}
                    initData={initData}
                  />
                )}
              </>
            )}
          </>
        )}
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
        />
      )}

      {/* Action Panel */}
      <ActionPanel
        buttons={actionButtons}
        visible={isActionPanelVisible}
      />
    </div>
  );
}

export default App;
