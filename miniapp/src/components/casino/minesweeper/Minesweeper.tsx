import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ApiService } from '../../../services/api';
import { TelegramUtils } from '../../../utils/telegram';
import AllCards from '../../cards/AllCards';
import CardModal from '../../cards/CardModal';
import AppLoading from '../../common/AppLoading';
import CasinoHeader from '../CasinoHeader';
import ActionPanel from '../../common/ActionPanel';
import { useModal, useOrientation } from '../../../hooks';
import { getIconObjectUrl } from '../../../lib/iconUrlCache';
import { getRarityGradient } from '../../../utils/rarityStyles';
import type { CardData } from '../../../types';
import type { ActionButton } from '../../common/ActionPanel';
import './Minesweeper.css';

interface MinesweeperProps {
  chatId: string;
  initData: string;
}

type GameState = 'loading' | 'selecting' | 'playing' | 'won' | 'lost';

interface GameData {
  gameId: number;
  status: string;
  betCardTitle: string;
  cardRarity: string;
  revealedCells: number[];
  movesCount: number;
  minePositions?: number[] | null;
  claimPointPositions?: number[] | null;
  cardIcon?: string | null;
  claimPointIcon?: string | null;
  mineIcon?: string | null;
  nextRefreshTime?: string | null;
  playerRevealedCells: number[];
}

const GRID_SIZE = 3;

const formatTimeUntilRefresh = (nextRefreshTime: string | null | undefined): string => {
  if (!nextRefreshTime) {
    return 'Refresh time unavailable';
  }

  try {
    const now = new Date();
    const refreshDate = new Date(nextRefreshTime);
    const diffMs = refreshDate.getTime() - now.getTime();

    if (diffMs <= 0) {
      return 'Next game available now!';
    }

    const diffMinutes = Math.floor(diffMs / 1000 / 60);
    const diffHours = Math.floor(diffMinutes / 60);

    if (diffMinutes < 1) {
      return 'Next game in <1m';
    } else if (diffHours > 0) {
      const remainingMinutes = diffMinutes % 60;
      return `Next game in ${diffHours}h ${remainingMinutes}m`;
    } else {
      return `Next game in ${diffMinutes}m`;
    }
  } catch {
    return 'Refresh time unavailable';
  }
};

const Minesweeper: React.FC<MinesweeperProps> = ({ chatId, initData }) => {
  const [gameState, setGameState] = useState<GameState>('loading');
  const [gameData, setGameData] = useState<GameData | null>(null);
  const [cards, setCards] = useState<CardData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const initializedRef = useRef(false);

  const { showModal, modalCard, openModal, closeModal } = useModal();
  const { orientation, orientationKey } = useOrientation();

  // Check for existing game and fetch cards on mount
  useEffect(() => {
    // Prevent duplicate initialization in React Strict Mode
    if (initializedRef.current) {
      return;
    }
    initializedRef.current = true;

    const initializeMinesweeper = async () => {
      try {
        setLoading(true);
        setError(null);
        
        // Get current user ID from Telegram
        const userData = TelegramUtils.initializeUser();
        if (!userData) {
          throw new Error('Could not initialize user data');
        }

        // Check if there's an existing game
        const existingGame = await ApiService.getMinesweeperGame(
          userData.currentUserId,
          chatId,
          initData
        );

        if (existingGame) {
          // Game exists, load it
          console.log('Existing minesweeper game found:', existingGame);
          setGameData({
            gameId: existingGame.game_id,
            status: existingGame.status,
            betCardTitle: existingGame.bet_card_title,
            cardRarity: existingGame.card_rarity,
            revealedCells: existingGame.revealed_cells,
            movesCount: existingGame.moves_count,
            minePositions: existingGame.mine_positions,
            claimPointPositions: existingGame.claim_point_positions,
            cardIcon: existingGame.card_icon,
            claimPointIcon: existingGame.claim_point_icon,
            mineIcon: existingGame.mine_icon,
            nextRefreshTime: existingGame.next_refresh_time,
            playerRevealedCells: existingGame.revealed_cells ?? []
          });
          
          // Set game state based on status
          if (existingGame.status === 'won') {
            setGameState('won');
          } else if (existingGame.status === 'lost') {
            setGameState('lost');
          } else {
            setGameState('playing');
          }
        } else {
          // No game exists, fetch user's cards for selection
          console.log('No existing game, fetching cards for selection');
          const response = await ApiService.fetchUserCards(
            userData.currentUserId,
            initData,
            chatId
          );
          
          // Filter out Unique cards
          const playableCards = response.cards.filter(card => card.rarity.toLowerCase() !== 'unique');
          
          setCards(playableCards);
          setGameState('selecting');
        }
      } catch (err) {
        console.error('Failed to initialize minesweeper:', err);
        const errorMessage = err instanceof Error ? err.message : 'Failed to load minesweeper';
        setError(errorMessage);
        setGameState('selecting');
      } finally {
        setLoading(false);
      }
    };

    void initializeMinesweeper();
  }, [chatId, initData]);

  // Update time display every second when game is over
  useEffect(() => {
    const isGameOver = gameState === 'won' || gameState === 'lost';
    if (isGameOver && gameData) {
      const interval = setInterval(() => {
        // Force re-render to update the time display
        setGameData(prev => prev ? { ...prev } : null);
      }, 1000); // Update every second

      return () => clearInterval(interval);
    }
  }, [gameState, gameData]);

  const handleSelectCard = useCallback(async () => {
    if (!modalCard) return;

    try {
      setLoading(true);
      closeModal();
      TelegramUtils.triggerHapticImpact('medium');

      // Get current user ID from Telegram
      const userData = TelegramUtils.initializeUser();
      if (!userData) {
        throw new Error('Could not initialize user data');
      }

      // Create new game with selected card
      console.log('Creating minesweeper game with card:', modalCard.id);
      const newGame = await ApiService.createMinesweeperGame(
        userData.currentUserId,
        chatId,
        modalCard.id,
        initData
      );

      console.log('Minesweeper game created:', newGame);
      setGameData({
        gameId: newGame.game_id,
        status: newGame.status,
        betCardTitle: newGame.bet_card_title,
        cardRarity: newGame.card_rarity,
        revealedCells: newGame.revealed_cells,
        movesCount: newGame.moves_count,
        minePositions: newGame.mine_positions,
        claimPointPositions: newGame.claim_point_positions,
        cardIcon: newGame.card_icon,
        claimPointIcon: newGame.claim_point_icon,
        mineIcon: newGame.mine_icon,
        nextRefreshTime: newGame.next_refresh_time,
        playerRevealedCells: newGame.revealed_cells ?? []
      });

      setGameState('playing');
      setError(null);
    } catch (err) {
      console.error('Failed to create minesweeper game:', err);
      const errorMessage = err instanceof Error ? err.message : 'Failed to create game';
      setError(errorMessage);
      TelegramUtils.showAlert(errorMessage);
    } finally {
      setLoading(false);
    }
  }, [modalCard, closeModal, chatId, initData]);

  const handleCellClick = async (row: number, col: number) => {
    if (gameState !== 'playing' || !gameData) return;
    
    const cellIndex = row * GRID_SIZE + col;
    console.log(`Cell clicked: ${row}, ${col} (index: ${cellIndex})`);
    
    // Check if cell already revealed
    if (gameData.revealedCells.includes(cellIndex)) {
      console.log('Cell already revealed, ignoring click');
      return;
    }
    
    try {
      // Get current user ID from Telegram
      const userData = TelegramUtils.initializeUser();
      if (!userData) {
        throw new Error('Could not initialize user data');
      }

      // Call update API
      console.log('Updating minesweeper game, revealing cell:', cellIndex);
      const updateResult = await ApiService.updateMinesweeperGame(
        userData.currentUserId,
        gameData.gameId,
        cellIndex,
        initData
      );

      console.log('Minesweeper game updated:', updateResult);

      // Show notification if claim point was awarded
      if (updateResult.claim_point_awarded) {
        TelegramUtils.showAlert('You received 1 claim point!');
      }

      // Update game data with new revealed cells
      setGameData(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          status: updateResult.status ?? prev.status,
          revealedCells: updateResult.revealed_cells,
          minePositions: updateResult.mine_positions ?? prev.minePositions,
          claimPointPositions: updateResult.claim_point_positions ?? prev.claimPointPositions,
          nextRefreshTime: updateResult.next_refresh_time ?? prev.nextRefreshTime,
          playerRevealedCells: Array.from(
            new Set([...(prev.playerRevealedCells ?? []), cellIndex])
          )
        };
      });

      const updatedStatus = updateResult.status ?? gameData?.status;
      const hitMine = updatedStatus === 'lost';

      if (hitMine) {
        TelegramUtils.triggerHapticNotification('error');
        TelegramUtils.triggerHapticImpact('heavy');
      } else {
        TelegramUtils.triggerHapticImpact('medium');
      }

      if (updatedStatus === 'lost') {
        console.log('Hit a mine! Game lost.');
        setGameState('lost');

        if (gameData?.betCardTitle) {
          TelegramUtils.showAlert(
            `Game Over!\n\nYou lost your ${gameData.betCardTitle}.`
          );
        }
      } else if (updatedStatus === 'won') {
        console.log('Won! Server reported victory.');
        setGameState('won');
        TelegramUtils.triggerHapticNotification('success');
        TelegramUtils.triggerHapticImpact('heavy');

        if (updateResult.bet_card_rarity && updateResult.source_display_name) {
          TelegramUtils.showAlert(
            `You Won!\n\nYou'll receive a ${updateResult.bet_card_rarity} ${updateResult.source_display_name}!`
          );
        }
      }
    } catch (err) {
      console.error('Failed to update minesweeper game:', err);
      const errorMessage = err instanceof Error ? err.message : 'Failed to update game';
      TelegramUtils.showAlert(errorMessage);
    }
  };

  const renderCell = (row: number, col: number) => {
    const cellIndex = row * GRID_SIZE + col;
    const isRevealed = gameData?.revealedCells.includes(cellIndex) ?? false;
    const hasMine = gameData?.minePositions?.includes(cellIndex) ?? false;
    const hasClaimPoint = gameData?.claimPointPositions?.includes(cellIndex) ?? false;
    const isLost = gameState === 'lost';
    const isGameOver = gameState === 'won' || gameState === 'lost';
    const isPlayerRevealed = gameData?.playerRevealedCells.includes(cellIndex) ?? false;

    let className = 'minesweeper-cell';

    if (!isRevealed && !isGameOver) {
      className += ' minesweeper-cell-hidden';
    } else {
      className += ' minesweeper-cell-revealed';
      if (isPlayerRevealed) {
        className += ' minesweeper-cell-player';
      }
    }

    if (isLost) {
      className += ' minesweeper-cell-lost';
    }

    const rarityGradient = gameData?.cardRarity ? getRarityGradient(gameData.cardRarity) : undefined;
    const rarityBorderColor = rarityGradient ? extractColorFromGradient(rarityGradient) : undefined;

    const shouldShowMine = hasMine && (isRevealed || isGameOver);
    const shouldShowClaim = !hasMine && hasClaimPoint && (isRevealed || isGameOver);
    const shouldShowSafe = !hasMine && !hasClaimPoint && (isRevealed || isGameOver);

    const canInteract = gameState === 'playing';

    return (
      <div
        key={`${row}-${col}`}
        className={className}
        onClick={canInteract ? () => handleCellClick(row, col) : undefined}
      >
        {shouldShowMine && gameData?.mineIcon && (
          <img
            src={getIconObjectUrl(gameData.mineIcon)}
            alt="Mine"
            className="minesweeper-cell-icon minesweeper-cell-icon-mine"
          />
        )}
        {shouldShowClaim && gameData?.claimPointIcon && (
          <img
            src={getIconObjectUrl(gameData.claimPointIcon)}
            alt="Claim Point"
            className="minesweeper-cell-icon minesweeper-cell-icon-claim"
          />
        )}
        {shouldShowSafe && gameData?.cardIcon && (
          <img
            src={getIconObjectUrl(gameData.cardIcon)}
            alt="Safe"
            className="minesweeper-cell-icon"
            style={rarityBorderColor ? { border: `3px solid ${rarityBorderColor}` } : {}}
          />
        )}
      </div>
    );
  };

  // Action buttons for card selection
  const getActionButtons = (): ActionButton[] => {
    if (gameState === 'selecting' && modalCard) {
      return [{
        id: 'select',
        text: 'Select',
        onClick: handleSelectCard,
        variant: 'primary',
        disabled: false
      }];
    }
    return [];
  };

  const actionButtons = getActionButtons();
  const isActionPanelVisible = actionButtons.length > 0;

  // Loading state
  if (loading || gameState === 'loading') {
    return <AppLoading title="💣 Minesweeper" />;
  }

  // Error state
  if (error) {
    return (
      <div className="minesweeper-container">
        <CasinoHeader title="Error" />
        <p>{error}</p>
      </div>
    );
  }

  // No cards available
  if (gameState === 'selecting' && cards.length === 0) {
    return (
      <div className="minesweeper-container">
        <CasinoHeader title="💣 Minesweeper" />
        <p>You don't have any cards to bet.</p>
      </div>
    );
  }

  // Card Selection View
  if (gameState === 'selecting') {
    return (
      <>
        <div className={`minesweeper-card-selection ${isActionPanelVisible ? 'with-action-panel' : ''}`}>
          <CasinoHeader title="💣 Minesweeper" />
          <p className="minesweeper-subtitle">Select a card to bet</p>

          <AllCards
            cards={cards}
            onCardClick={openModal}
            initData={initData}
          />
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

        {/* Action Panel */}
        <ActionPanel
          buttons={actionButtons}
          visible={isActionPanelVisible}
        />
      </>
    );
  }

  // Helper to extract a single color from gradient for borders
  const extractColorFromGradient = (gradient: string): string => {
    // Extract first hex color from gradient string
    const match = gradient.match(/#[0-9a-fA-F]{6}/);
    return match ? match[0] : '#3498db';
  };

  // Game Board View
  const rarityGradient = gameData?.cardRarity ? getRarityGradient(gameData.cardRarity) : undefined;
  const rarityBorderColor = rarityGradient ? extractColorFromGradient(rarityGradient) : '#3498db';

  return (
    <div className="minesweeper-container">
      <CasinoHeader title="💣 Minesweeper" />
      {gameData && (
        <p 
          className="minesweeper-bet-info"
          style={{
            background: rarityGradient,
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text'
          }}
        >
          Bet: {gameData.cardRarity} {gameData.betCardTitle}
        </p>
      )}
      
      <div className={`minesweeper-game ${gameState === 'won' ? 'minesweeper-game-won' : ''} ${gameState === 'lost' ? 'minesweeper-game-lost' : ''}`} style={{ borderColor: rarityBorderColor }}>
  <div className={`minesweeper-grid ${gameState === 'won' ? 'minesweeper-grid-won' : ''} ${gameState === 'lost' ? 'minesweeper-grid-lost' : ''} ${gameState !== 'playing' ? 'minesweeper-grid-disabled' : ''}`}>
          {Array.from({ length: GRID_SIZE }).map((_, rowIndex) => (
            <div key={rowIndex} className="minesweeper-row">
              {Array.from({ length: GRID_SIZE }).map((_, colIndex) => 
                renderCell(rowIndex, colIndex)
              )}
            </div>
          ))}
        </div>
      </div>

      {gameState === 'won' && (
        <p className="minesweeper-status minesweeper-status-won">🎉 Game Won!</p>
      )}
      {gameState === 'lost' && (
        <p className="minesweeper-status minesweeper-status-lost">💥 Game Over!</p>
      )}

      {(gameState === 'won' || gameState === 'lost') && gameData && (
        <div className="minesweeper-refresh-hint">
          {formatTimeUntilRefresh(gameData.nextRefreshTime)}
        </div>
      )}
    </div>
  );
};

export default Minesweeper;
