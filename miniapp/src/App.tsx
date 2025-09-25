import { useState, useCallback, useEffect, useRef } from 'react';
import './App.css';

// Components
import Card from './components/Card';
import AllCards from './components/AllCards';
import CardModal from './components/CardModal';

// Hooks
import {
  useCards,
  useAllCards,
  useOrientation,
  useModal,
  useMainButton,
  useSwipeHandlers
} from './hooks';

// Utils
import { TelegramUtils } from './utils/telegram';

// Types
import type { CardData, View } from './types';

// Build info
import { BUILD_INFO } from './build-info';

function App() {
  // Log build info to console for debugging
  console.log('App build info:', BUILD_INFO);
  
  // Core data hooks
  const { cards, loading, error, userData, initData } = useCards();
  
  // UI state
  const [currentIndex, setCurrentIndex] = useState(0);
  const [view, setView] = useState<View>('current');
  const [selectedCardForTrade, setSelectedCardForTrade] = useState<CardData | null>(null);
  const [isTradeGridActive, setIsTradeGridActive] = useState(false);

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

  const displayedCards = isTradeView && selectedCardForTrade
    ? allCards.filter((card) => card.id !== selectedCardForTrade.id)
    : allCards;
  
  // Feature hooks
  const { orientation, orientationKey, resetTiltReference } = useOrientation();
  const { showModal, modalCard, openModal, closeModal } = useModal();

  const exitTradeView = useCallback(() => {
    setIsTradeGridActive(false);
    setSelectedCardForTrade(null);
    closeModal();
    setView('current');
    TelegramUtils.hideBackButton();
  }, [closeModal]);

  const exitTradeViewRef = useRef(exitTradeView);

  useEffect(() => {
    exitTradeViewRef.current = exitTradeView;
  }, [exitTradeView]);
  
  // Memoized callback functions to prevent infinite re-renders
  const handleTradeClick = useCallback(() => {
    // Handle trade button click in current view (only if trading is enabled)
    if (userData?.enableTrade && cards[currentIndex]) {
      const tradeCard = cards[currentIndex];

      if (!tradeCard.chat_id) {
        TelegramUtils.showAlert('This card cannot be traded because it is not associated with a chat yet.');
        return;
      }

      setSelectedCardForTrade(tradeCard);
      const cardName = `${tradeCard.modifier} ${tradeCard.base_name}`;
      TelegramUtils.showAlert(
        hasChatScope
          ? `Choose the card to trade ${cardName} for in All view`
          : `Choose a card from this chat to trade ${cardName} for`
      );
      setIsTradeGridActive(!hasChatScope);
      setView('all');
    }
  }, [cards, currentIndex, userData?.enableTrade, hasChatScope]);

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
  }, [exitTradeView]);

  const handleAllTabClick = useCallback(() => {
    setIsTradeGridActive(false);
    setSelectedCardForTrade(null);
    setView('all');
  }, []);

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
  
  // Effects
  const { isMainButtonVisible } = useMainButton(
    loading,
    error,
    userData?.isOwnCollection ?? false,
    userData?.enableTrade ?? false,
    cards.length > 0, 
    view,
    selectedCardForTrade,
    modalCard,
    handleTradeClick,
    handleSelectClick
  );

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

  const handleDotClick = (index: number) => {
    if (index !== currentIndex) {
      setCurrentIndex(index);
      resetTiltReference();
    }
  };

  // Loading state
  if (loading) {
    return <div className="app-container"><h1>Loading cards...</h1></div>;
  }

  // Error state
  if (error) {
    return <div className="app-container"><h1>Error: {error}</h1></div>;
  }

  return (
    <div className="app-container" {...(view === 'current' ? swipeHandlers : {})}>
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
        <h1 className="app-title">
          {view === 'all'
            ? isTradeView && tradeCardName
              ? `Trade for ${tradeCardName}`
              : 'All cards'
            : `${collectionOwnerLabel}'s collection`}
        </h1>
        
        {/* Current View */}
        {view === 'current' && (
          <>
            {cards.length > 0 ? (
              <div className={`card-container ${isMainButtonVisible ? 'with-trade-button' : ''}`}>
                {/* Navigation Dots */}
                <div className="navigation-dots" style={{ marginBottom: '2vh' }}>
                  {cards.map((_, index) => (
                    <span
                      key={index}
                      className={`dot ${currentIndex === index ? 'active' : ''}`}
                      onClick={() => handleDotClick(index)}
                    />
                  ))}
                </div>
                
                {/* Current Card */}
                <Card 
                  {...cards[currentIndex]} 
                  orientation={orientation}
                  tiltKey={orientationKey}
                  initData={initData}
                  shiny={true}
                />
              </div>
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
            ) : displayedCards.length === 0 ? (
              <div className="no-cards-container">
                <h2>{isTradeView ? 'No trade options' : 'No cards found'}</h2>
                <p>
                  {isTradeView
                    ? 'No other cards are available in this chat right now.'
                    : 'There are no cards in the system yet.'}
                </p>
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
        />
      )}
    </div>
  );
}

export default App;
