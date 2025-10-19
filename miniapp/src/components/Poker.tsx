import React, { useState, useEffect, useRef } from 'react';
import { usePokerStore } from '../stores/usePokerStore';
import { PokerWebSocket } from '../services/PokerWebSocket';
import './Poker.css';

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
  const wsRef = useRef<PokerWebSocket | null>(null);

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

    // Cleanup on unmount
    return () => {
      if (wsRef.current) {
        wsRef.current.disconnect();
        wsRef.current = null;
      }
      usePokerStore.getState().reset();
    };
  }, [chatId, initData]);

  // Calculate circular positions for players around the table
  const getPlayerPosition = (index: number, total: number) => {
    const angle = (index * 360) / total - 90; // Start from top
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
    } catch (error) {
      console.error('Failed to reset game:', error);
      usePokerStore.getState().setError('Failed to reset game');
    }
  };

  const players = gameState?.players || [];

  return (
    <div className="poker-container" style={{ position: 'relative' }}>
      <h1>🃏 Poker</h1>

      {connectionStatus === 'connecting' && !error && (
        <div style={{ color: '#888', marginBottom: '10px' }}>
          Connecting...
        </div>
      )}
      
      <div className="poker-game">
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
            
            {/* Dynamic player icons */}
            {players.map((player, index) => {
              const { x, y } = getPlayerPosition(index, players.length);
              // Use cached slot icon from store
              const slotIcon = playerSlotIcons[player.user_id];
              return (
                <div
                  key={player.user_id}
                  className="player-icon"
                  style={{
                    left: '50%',
                    top: '50%',
                    transform: `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`,
                    backgroundImage: slotIcon 
                      ? `url(data:image/png;base64,${slotIcon})`
                      : undefined,
                    backgroundSize: 'cover',
                    backgroundPosition: 'center',
                  }}
                  title={`Player ${player.user_id}`}
                />
              );
            })}
          </div>
        </div>
        
        <div className="poker-action-space">
          <button 
            className="poker-join-button"
            disabled={loading || !connected}
            onClick={handleJoin}
          >
            {loading ? 'Joining...' : 'Join'}
          </button>
          
          <button 
            className="poker-reset-button"
            disabled={!connected}
            onClick={handleReset}
            style={{
              marginTop: '10px',
              padding: '8px 16px',
              backgroundColor: '#ff4444',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: connected ? 'pointer' : 'not-allowed',
              opacity: connected ? 1 : 0.5,
              fontSize: '14px',
            }}
          >
            Reset Game (Debug)
          </button>
        </div>
      </div>

      {error && (
        <div className="poker-error" style={{ 
          position: 'absolute',
          bottom: '30px',
          left: '50%',
          transform: 'translateX(-50%)',
          color: '#ff6b6b', 
          fontSize: '13px',
          fontWeight: 'bold',
          textAlign: 'center',
          width: 'calc(100% - 40px)',
          maxWidth: '350px',
          opacity: 0.85,
          textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)',
        }}>
          {error}
        </div>
      )}
    </div>
  );
};

export default Poker;
