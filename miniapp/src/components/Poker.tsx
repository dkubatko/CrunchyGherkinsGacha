import React, { useState, useEffect, useRef } from 'react';
import { usePokerStore } from '../stores/usePokerStore';
import { PokerWebSocket } from '../services/PokerWebSocket';
import './Poker.css';
import cardBackImage from '../assets/casino/card_back.png';

interface PokerProps {
  chatId: string;
  initData: string;
}

interface TelegramWebApp {
  initDataUnsafe?: {
    user?: {
      id?: number;
    };
  };
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
  }
}

const Poker: React.FC<PokerProps> = ({ chatId, initData }) => {
  const [loading, setLoading] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [showDebugMenu, setShowDebugMenu] = useState(false);
  const [fakePlayers, setFakePlayers] = useState<Array<{ user_id: number }>>([]);
  const wsRef = useRef<PokerWebSocket | null>(null);
  const countdownIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const debugMenuRef = useRef<HTMLDivElement | null>(null);

  // Get state from Zustand store
  const { connectionStatus, error, gameState, playerSlotIcons } = usePokerStore();
  const connected = connectionStatus === 'connected';

  // Initialize WebSocket connection
  useEffect(() => {
    if (!chatId || !initData) {
      usePokerStore.getState().setError('Missing chat ID or initialization data');
      return;
    }

    const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
    if (!userId) {
      usePokerStore.getState().setError('Failed to get user ID from Telegram');
      return;
    }

    // Only create WebSocket if we don't have one
    if (!wsRef.current) {
      const ws = new PokerWebSocket(chatId, userId, initData);
      wsRef.current = ws;
      ws.connect();
    }

    // Handle page unload / app close
    const handleBeforeUnload = () => {
      if (wsRef.current) {
        wsRef.current.disconnect();
      }
    };

    // Handle visibility change (when user switches tabs or minimizes app)
    const handleVisibilityChange = () => {
      if (document.hidden && wsRef.current) {
        // User navigated away or minimized - disconnect
        wsRef.current.disconnect();
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    // Cleanup on unmount
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      
      if (wsRef.current) {
        wsRef.current.disconnect();
        wsRef.current = null;
      }
      usePokerStore.getState().reset();
    };
  }, [chatId, initData]);

  // Manage countdown timer based on game state
  useEffect(() => {
    // Clear any existing interval
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current);
      countdownIntervalRef.current = null;
    }

    if (!gameState) {
      setCountdown(null);
      return;
    }

    // If game is in countdown status
    if (gameState.status === 'countdown' && gameState.countdown_start_time) {
      const startTime = new Date(gameState.countdown_start_time).getTime();
      const countdownDuration = gameState.countdown_duration_seconds || 60; // fallback to 60s
      
      const updateCountdown = () => {
        const now = Date.now();
        const elapsed = (now - startTime) / 1000; // seconds
        const remaining = Math.max(0, Math.ceil(countdownDuration - elapsed));
        
        setCountdown(remaining);
        
        // Stop the interval when countdown reaches 0
        if (remaining <= 0 && countdownIntervalRef.current) {
          clearInterval(countdownIntervalRef.current);
          countdownIntervalRef.current = null;
        }
      };

      // Update immediately
      updateCountdown();
      
      // Then update every 100ms for smooth countdown
      countdownIntervalRef.current = setInterval(updateCountdown, 100);
    } else if (gameState.status === 'playing') {
      // Game has started
      setCountdown(null);
    } else {
      // Waiting status
      setCountdown(null);
    }

    // Cleanup interval on unmount or when dependencies change
    return () => {
      if (countdownIntervalRef.current) {
        clearInterval(countdownIntervalRef.current);
        countdownIntervalRef.current = null;
      }
    };
  }, [gameState]);

  // Close debug menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (debugMenuRef.current && !debugMenuRef.current.contains(event.target as Node)) {
        setShowDebugMenu(false);
      }
    };

    if (showDebugMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showDebugMenu]);

  // Calculate circular positions for players around the table
  // Index 0 is always anchored at the bottom (90 degrees)
  const getPlayerPosition = (index: number, total: number) => {
    const angle = (index * 360) / total + 90; // Start from bottom (90°), distribute clockwise
    const radius = 140; // Distance from center of table (250px table / 2 + spacing)
    const angleRad = (angle * Math.PI) / 180;
    const x = radius * Math.cos(angleRad);
    const y = radius * Math.sin(angleRad);
    return { x, y };
  };

  const handleJoin = () => {
    if (!wsRef.current || !wsRef.current.isConnected()) {
      usePokerStore.getState().setError('Not connected to server');
      return;
    }

    setLoading(true);
    usePokerStore.getState().setError(null);

    // Get user's spin balance (TODO: Get actual balance from API or state)
    const spinBalance = 100;

    wsRef.current.join(spinBalance);

    // Loading state will be cleared when we receive the updated game state
    setTimeout(() => setLoading(false), 2000);
  };

  const handleReset = async () => {
    if (!wsRef.current) {
      usePokerStore.getState().setError('Not connected to server');
      return;
    }

    if (!window.confirm('Reset the poker game? This will remove all players.')) {
      return;
    }

    try {
      await wsRef.current.reset();
      usePokerStore.getState().setError(null);
      // Clear fake players on reset
      setFakePlayers([]);
    } catch (error) {
      console.error('Failed to reset game:', error);
      usePokerStore.getState().setError('Failed to reset game');
    }
  };

  const handleAddFakePlayer = () => {
    // Generate a random fake user ID (negative to avoid conflicts with real users)
    const fakeUserId = -Math.floor(Math.random() * 10000);
    setFakePlayers(prev => [...prev, { user_id: fakeUserId }]);
  };

  const players = gameState?.players || [];
  const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
  const currentPlayer = userId ? players.find(p => p.user_id === userId) : undefined;

  // Reorder players so current user is always at index 0 (bottom of table)
  const getRotatedPlayers = () => {
    const allPlayers = [...players, ...fakePlayers];
    if (!userId || allPlayers.length === 0) return allPlayers;
    
    const currentUserIndex = allPlayers.findIndex(p => p.user_id === userId);
    if (currentUserIndex === -1) return allPlayers;
    
    // Rotate array so current user is at index 0 (which is anchored at bottom)
    return [
      ...allPlayers.slice(currentUserIndex),
      ...allPlayers.slice(0, currentUserIndex)
    ];
  };

  // Helper to get rarity class name
  const getRarityClass = (rarity: string): string => {
    return `rarity-${rarity.toLowerCase()}`;
  };

  return (
    <div className="poker-container">
      <h1>🃏 Poker</h1>

      {/* Dynamic styles for player icons and cards - keeps base64 out of inspector */}
      <style>
        {playerSlotIcons && Object.entries(playerSlotIcons).map(([userId, icon]) => (
          `.player-icon[data-user-id="${userId}"] { background-image: url(data:image/png;base64,${icon}); }`
        )).join('\n')}
        {currentPlayer?.hole_cards?.map((card, index) => (
          `.current-player-card[data-card-index="${index}"] { background-image: url(data:image/png;base64,${card.poker_cardb64}); }`
        )).join('\n')}
      </style>

      <div className="poker-game">
        {/* Debug Settings Button */}
        <div ref={debugMenuRef}>
          <button 
            className="poker-debug-button"
            onClick={() => setShowDebugMenu(!showDebugMenu)}
            title="Debug Settings"
          >
            ⚙️
          </button>
          
          {/* Debug Menu Dropdown */}
          {showDebugMenu && (
            <div className="poker-debug-menu">
              <button 
                className="poker-debug-menu-item"
                onClick={() => {
                  handleAddFakePlayer();
                  setShowDebugMenu(false);
                }}
              >
                Add Player
              </button>
              <button 
                className="poker-debug-menu-item"
                disabled={!connected}
                onClick={() => {
                  handleReset();
                  setShowDebugMenu(false);
                }}
              >
                Reset Game
              </button>
            </div>
          )}
        </div>
        
        <div className="poker-game-space">
          <div className="poker-table-wrapper">
            <div className="poker-table">
              <div className="community-cards">
                <div className="card-outline"></div>
                <div className="card-outline"></div>
                <div className="card-outline"></div>
                <div className="card-outline"></div>
                <div className="card-outline"></div>
              </div>
            </div>
            
            {/* Dynamic player icons - rotated so current user is at bottom */}
            {getRotatedPlayers().map((player, index) => {
              const totalPlayers = players.length + fakePlayers.length;
              const { x, y } = getPlayerPosition(index, totalPlayers);
              const isCurrentUser = player.user_id === userId;
              const isPlaying = gameState?.status === 'playing' || gameState?.status === 'pre_flop';
              const showCards = isPlaying;
              
              // Calculate angle from center to player
              const angleFromCenter = Math.atan2(y, x) * (180 / Math.PI);
              
              // Calculate offset towards center along the radial axis
              const inwardDistance = 30; // Distance to shift towards center (reduced to move cards further from center)
              const offsetX = -Math.cos(angleFromCenter * Math.PI / 180) * inwardDistance;
              const offsetY = -Math.sin(angleFromCenter * Math.PI / 180) * inwardDistance;
              
              // Get player's actual cards if they're the current user
              const playerCards = isCurrentUser && currentPlayer?.hole_cards ? currentPlayer.hole_cards : null;
              
              return (
                <div
                  key={player.user_id}
                  className="player-container"
                  style={{
                    position: 'absolute',
                    left: '50%',
                    top: '50%',
                    transform: `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`,
                  }}
                >
                  {/* Player icon stays upright */}
                  <div
                    className="player-icon"
                    data-user-id={player.user_id}
                    title={`Player ${player.user_id}`}
                  />
                  
                  {/* Player cards - shown when game is playing */}
                  {showCards && (
                    <div 
                      className={`hole-cards ${isCurrentUser ? 'current-player-cards' : ''}`}
                      style={{
                        // Center the container, move towards center, then rotate to face center
                        transform: `translate(calc(-50% + ${offsetX}px), calc(-50% + ${offsetY}px)) rotate(${angleFromCenter - 90}deg)`,
                      }}
                    >
                      {isCurrentUser && playerCards ? (
                        // Current user sees their actual cards with rarity borders
                        <>
                          <div 
                            className={`hole-card hole-card-left current-player-card ${getRarityClass(playerCards[0].rarity)}`}
                            data-card-index="0"
                          />
                          {playerCards[1] && (
                            <div 
                              className={`hole-card hole-card-right current-player-card ${getRarityClass(playerCards[1].rarity)}`}
                              data-card-index="1"
                            />
                          )}
                        </>
                      ) : (
                        // Other players see card backs
                        <>
                          <div className="hole-card hole-card-left">
                            <img src={cardBackImage} alt="Card back" />
                          </div>
                          <div className="hole-card hole-card-right">
                            <img src={cardBackImage} alt="Card back" />
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
        
        <div className="poker-action-space">
          {/* Left side - game status and actions */}
          <div className="poker-action-left">
            {(() => {
              const hasJoined = userId && players.some(p => p.user_id === userId);
              
              if (hasJoined) {
                // User has joined - show status
                if (gameState?.status === 'playing' || gameState?.status === 'pre_flop') {
                  return (
                    <div className="poker-status-container">
                      <div className="poker-game-started">
                        Game Started
                      </div>
                    </div>
                  );
                } else if (gameState?.status === 'countdown' && countdown !== null) {
                  return (
                    <div className="poker-status-container">
                      <div className="poker-countdown">
                        {countdown}s
                      </div>
                      <div className="poker-countdown-label">
                        until game start
                      </div>
                    </div>
                  );
                } else {
                  // Waiting status
                  return (
                    <div className="poker-status-container">
                      <div className="poker-waiting-message">
                        Waiting for other players...
                      </div>
                    </div>
                  );
                }
              } else {
                // User hasn't joined yet - show join button
                return (
                  <button 
                    className="poker-join-button"
                    disabled={loading || !connected}
                    onClick={handleJoin}
                  >
                    {loading ? 'Joining...' : 'Join'}
                  </button>
                );
              }
            })()}
          </div>

          {/* Right side - reserved for future actions/buttons */}
          <div className="poker-action-right">
          </div>
        </div>
      </div>

      {(error || connectionStatus === 'connecting') && (
        <div className="poker-status">
          {error || 'Connecting...'}
        </div>
      )}
    </div>
  );
};

export default Poker;
