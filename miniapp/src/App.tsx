import { useState, useCallback } from 'react';
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

function App() {
  // Core data hooks
  const { cards, loading, error, userData, authToken } = useCards();
  const { allCards, loading: allCardsLoading, error: allCardsError, refetch: refetchAllCards } = useAllCards(authToken);
  
  // UI state
  const [currentIndex, setCurrentIndex] = useState(0);
  const [view, setView] = useState<View>('current');
  const [selectedCardForTrade, setSelectedCardForTrade] = useState<CardData | null>(null);
  
  // Feature hooks
  const { orientation, orientationKey, resetTiltReference } = useOrientation();
  const { showModal, modalCard, openModal, closeModal } = useModal();
  
  // Memoized callback functions to prevent infinite re-renders
  const handleTradeClick = useCallback(() => {
    // Handle trade button click in current view
    if (cards[currentIndex]) {
      setSelectedCardForTrade(cards[currentIndex]);
      const cardName = `${cards[currentIndex].modifier} ${cards[currentIndex].base_name}`;
      // Show alert and switch to All view
      TelegramUtils.showAlert(`Choose the card to trade ${cardName} for in All view`);
      setView('all');
    }
  }, [cards, currentIndex]);

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
              'Authorization': `Bearer ${authToken}`
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
      setSelectedCardForTrade(null);
      closeModal();
    }
  }, [selectedCardForTrade, modalCard, authToken, closeModal]);
  
  // Effects
  const { isMainButtonVisible } = useMainButton(
    loading, 
    error, 
    userData?.isOwnCollection ?? false, 
    cards.length > 0, 
    view,
    selectedCardForTrade,
    modalCard,
    handleTradeClick,
    handleSelectClick
  );
  
  // Event handlers
  const swipeHandlers = useSwipeHandlers({
    cardsLength: cards.length,
    currentIndex,
    onIndexChange: setCurrentIndex,
    onTiltReset: resetTiltReference
  });

  const handleCardClick = (card: CardData) => {
    // Always show card in modal regardless of ownership
    openModal(card);
  };

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
          onClick={() => setView('current')}
        >
          Current
        </button>
        <button 
          className={`tab ${view === 'all' ? 'active' : ''}`} 
          onClick={() => setView('all')}
        >
          All
        </button>
      </div>

      <div className="app-content">
        <h1 className="app-title">
          {view === 'all' ? 'All cards' : `@${userData?.username}'s collection`}
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
                  authToken={authToken}
                  shiny={true}
                />
              </div>
            ) : (
              <p>
                {userData?.isOwnCollection 
                  ? "You don't own any cards yet." 
                  : `@${userData?.username} doesn't own any cards yet.`
                }
              </p>
            )}
          </>
        )}

        {/* All Cards View */}
        {view === 'all' && (
          <>
            {allCardsLoading ? (
              <div className="loading-container">
                <h2>Loading all cards...</h2>
              </div>
            ) : allCardsError ? (
              <div className="error-container">
                <h2>Error loading cards</h2>
                <p>{allCardsError}</p>
                <button onClick={refetchAllCards}>Retry</button>
              </div>
            ) : allCards.length === 0 ? (
              <div className="no-cards-container">
                <h2>No cards found</h2>
                <p>There are no cards in the system yet.</p>
              </div>
            ) : (
              <AllCards 
                cards={allCards} 
                onCardClick={handleCardClick}
                authToken={authToken}
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
          authToken={authToken}
          onClose={closeModal}
        />
      )}
    </div>
  );
}

export default App;
