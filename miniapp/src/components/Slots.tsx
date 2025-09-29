import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { ApiService } from '../services/api';
import { TelegramUtils } from '../utils/telegram';
import type { ChatUserCharacterSummary } from '../types';
import './SlotMachine.css';

interface SlotsProps {
  userId: number;
  chatId: string;
}

interface SlotSymbol {
  id: number;
  iconb64?: string;
  displayName?: string;
  type: 'user' | 'character';
}

interface SpinState {
  spinning: boolean;
  reelStates: ('idle' | 'fast' | 'slow' | 'stopped')[];
  results: number[];
}

interface RaritySpinState {
  visible: boolean;
  spinning: boolean;
  result: number;
}

const Slots: React.FC<SlotsProps> = ({ chatId }) => {
  const [usersAndCharacters, setUsersAndCharacters] = useState<ChatUserCharacterSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [spinState, setSpinState] = useState<SpinState>({
    spinning: false,
    reelStates: ['idle', 'idle', 'idle'],
    results: [0, 1, 2] // Default indices to show first 3 symbols
  });
  const [raritySpinState, setRaritySpinState] = useState<RaritySpinState>({
    visible: false,
    spinning: false,
    result: 0
  });
  
  const symbols = useRef<SlotSymbol[]>([]);
  const reelTimeouts = useRef<NodeJS.Timeout[]>([]);
  const rarityTimeouts = useRef<NodeJS.Timeout[]>([]);
  
  const rarityOptions = useMemo(() => [
    { name: 'Common', color: '#3498db', emoji: '⚪' }, // Blue
    { name: 'Rare', color: '#2ecc71', emoji: '�' },   // Green
    { name: 'Epic', color: '#9b59b6', emoji: '🟣' },   // Purple
    { name: 'Legendary', color: '#f39c12', emoji: '🟡' } // Gold
  ], []);

  useEffect(() => {
    const fetchUsersAndCharacters = async () => {
      try {
        setLoading(true);
        setError(null);

        const initData = TelegramUtils.getInitData();
        if (!initData) {
          throw new Error('No Telegram init data found');
        }

        const data = await ApiService.fetchChatUsersAndCharacters(chatId, initData);
        setUsersAndCharacters(data);
        
        // Convert to symbols and ensure we have at least 3 for the slot machine
        const convertedSymbols: SlotSymbol[] = data
          .filter(item => item.slot_iconb64) // Only use items with icons
          .map(item => ({
            id: item.id,
            iconb64: item.slot_iconb64 || undefined,
            displayName: item.display_name || `${item.type} ${item.id}`,
            type: item.type
          }));

        // If we have less than 3 symbols, duplicate them to ensure we have enough
        while (convertedSymbols.length < 3) {
          convertedSymbols.push(...convertedSymbols.slice(0, Math.min(3 - convertedSymbols.length, convertedSymbols.length)));
        }

        symbols.current = convertedSymbols;
        
        // Set initial results to show the first 3 different symbols if available
        const initialResults = convertedSymbols.length >= 3 
          ? [0, 1, 2] 
          : [0, 0, 0];
          
        setSpinState(prev => ({
          ...prev,
          results: initialResults
        }));
        
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred';
        setError(errorMessage);
      } finally {
        setLoading(false);
      }
    };

    if (chatId) {
      fetchUsersAndCharacters();
    } else {
      setError('No chat ID provided');
      setLoading(false);
    }

    // Cleanup function to prevent memory leaks
    return () => {
      reelTimeouts.current.forEach(timeout => clearTimeout(timeout));
      reelTimeouts.current = [];
      rarityTimeouts.current.forEach(timeout => clearTimeout(timeout));
      rarityTimeouts.current = [];
    };
  }, [chatId]);

  const generateRandomResults = (): number[] => {
    const availableSymbols = symbols.current.length;
    if (availableSymbols === 0) return [0, 0, 0];
    
    // Generate truly random results for each reel
    return [
      Math.floor(Math.random() * availableSymbols),
      Math.floor(Math.random() * availableSymbols),
      Math.floor(Math.random() * availableSymbols)
    ];
  };

  const startRaritySpinner = useCallback(() => {
    // Clear any existing rarity timeouts
    rarityTimeouts.current.forEach(timeout => clearTimeout(timeout));
    rarityTimeouts.current = [];

    // Generate weighted random result (more common rarities have higher chance)
    const weights = [50, 30, 15, 5]; // Common, Rare, Epic, Legendary
    const totalWeight = weights.reduce((sum, weight) => sum + weight, 0);
    const random = Math.random() * totalWeight;
    
    let result = 0;
    let cumulativeWeight = 0;
    for (let i = 0; i < weights.length; i++) {
      cumulativeWeight += weights[i];
      if (random <= cumulativeWeight) {
        result = i;
        break;
      }
    }

    // Show and start spinning immediately
    setRaritySpinState({
      visible: true,
      spinning: true,
      result
    });

    // Spin for 2 seconds, then show win notification using WebApp
    const stopSpinTimeout = setTimeout(() => {
      // First stop the fast spinning animation
      setRaritySpinState(prev => ({
        ...prev,
        spinning: false
      }));
      
      // After a brief moment, show the win notification using TelegramUtils
      const showNotificationTimeout = setTimeout(() => {
        const winningSymbol = symbols.current[spinState.results[0]];
        const rarity = rarityOptions[result].name;
        const winnerName = winningSymbol?.displayName || 'Unknown';
        
        // Use TelegramUtils to show alert and close app
        TelegramUtils.showAlert(`Won ${rarity} ${winnerName}!`);
        
        // Close the miniapp after showing the alert
        setTimeout(() => {
          TelegramUtils.closeApp();
        }, 100);
      }, 500);
      
      rarityTimeouts.current.push(showNotificationTimeout);
    }, 2000);

    rarityTimeouts.current.push(stopSpinTimeout);
  }, [spinState.results, rarityOptions]);

  const stopReel = useCallback((reelIndex: number, finalResult: number) => {
    setSpinState(prev => {
      const newReelStates = [...prev.reelStates];
      const newResults = [...prev.results];
      
      newReelStates[reelIndex] = 'slow';
      newResults[reelIndex] = finalResult;
      
      // Enable spin button immediately when the last reel (index 2) stops
      const isLastReel = reelIndex === 2;
      
      return {
        ...prev,
        reelStates: newReelStates,
        results: newResults,
        spinning: !isLastReel // Enable spin button when last reel starts slowing down
      };
    });

    // After slow animation, set to stopped (visual state only, doesn't affect spinning)
    setTimeout(() => {
      setSpinState(prev => {
        const newReelStates = [...prev.reelStates];
        newReelStates[reelIndex] = 'stopped';
        
        // Check if all reels are stopped and if it's a win
        const allStopped = newReelStates.every(state => state === 'stopped');
        
        if (allStopped && prev.results[0] === prev.results[1] && prev.results[1] === prev.results[2]) {
          // Use setTimeout to ensure state update happens first
          setTimeout(() => startRaritySpinner(), 0);
        }
        
        return {
          ...prev,
          reelStates: newReelStates
          // Don't change spinning here - it's already false
        };
      });
    }, 300);
  }, [startRaritySpinner]);

  const handleSpin = useCallback(() => {
    if (spinState.spinning || symbols.current.length === 0) return;

    // Clear any existing timeouts
    reelTimeouts.current.forEach(timeout => clearTimeout(timeout));
    reelTimeouts.current = [];
    rarityTimeouts.current.forEach(timeout => clearTimeout(timeout));
    rarityTimeouts.current = [];

    // Hide rarity spinner only when starting a new spin
    setRaritySpinState({
      visible: false,
      spinning: false,
      result: 0
    });

    // Generate final results
    const finalResults = generateRandomResults();
    
    // Set all reels to spinning fast
    setSpinState({
      spinning: true,
      reelStates: ['fast', 'fast', 'fast'],
      results: finalResults
    });

    // Stop reels with staggered timing (left to right)
    [0, 1, 2].forEach((reelIndex) => {
      const timeout = setTimeout(() => {
        stopReel(reelIndex, finalResults[reelIndex]);
      }, 1000 + reelIndex * 300); // 1s base + 300ms stagger per reel

      reelTimeouts.current.push(timeout);
    });
  }, [spinState.spinning, stopReel]);

  // Memoize reel symbols to prevent unnecessary recalculations
  const getReelSymbols = useCallback((reelIndex: number): SlotSymbol[] => {
    if (symbols.current.length === 0) return [];
    
    const result = spinState.results[reelIndex];
    const extended: SlotSymbol[] = [];
    
    // Create sequence to show result symbol in the MIDDLE position
    // With translateY(0), we need: [top, MIDDLE (result), bottom]
    const topIndex = (result - 1 + symbols.current.length) % symbols.current.length;
    const middleIndex = result;
    const bottomIndex = (result + 1) % symbols.current.length;
    
    extended.push(symbols.current[topIndex]);    // Will be at top (90px from viewport top)
    extended.push(symbols.current[middleIndex]); // Will be in middle (90-180px) - THE SELECTED ONE
    extended.push(symbols.current[bottomIndex]); // Will be at bottom (180-270px)
    
    return extended;
  }, [spinState.results]);

  const getReelTransform = (reelIndex: number): string => {
    const state = spinState.reelStates[reelIndex];
    
    switch (state) {
      case 'idle':
      case 'stopped':
        return 'translateY(0px)'; // Show all 3 symbols with result in middle position
      case 'fast':
        return 'translateY(0px)'; // Will be animated by CSS
      case 'slow':
        return 'translateY(0px)'; // Animate to final position
      default:
        return 'translateY(0px)';
    }
  };

  const getReelClassName = (reelIndex: number): string => {
    const state = spinState.reelStates[reelIndex];
    const baseClass = 'slot-reel';
    
    switch (state) {
      case 'fast':
        return `${baseClass} spinning reel-spinning-fast`;
      case 'slow':
        return `${baseClass} spinning reel-spinning-slow`;
      default:
        return baseClass;
    }
  };

  const checkForWin = (): boolean => {
    const { results } = spinState;
    if (results.length !== 3 || symbols.current.length === 0) return false;
    
    // Check if all three results are the same
    return results[0] === results[1] && results[1] === results[2];
  };

  const isWinning = !spinState.spinning && checkForWin();

  if (loading) {
    return (
      <div className="slots-container">
        <h1>🎰 Slots</h1>
        <div className="slot-machine-container">
          <p>Loading slot machine...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="slots-container">
        <h1>🎰 Slots</h1>
        <div className="slot-machine-container">
          <p>Error: {error}</p>
          <p>Chat ID: {chatId}</p>
        </div>
      </div>
    );
  }

  if (symbols.current.length === 0) {
    return (
      <div className="slots-container">
        <h1>🎰 Slots</h1>
        <div className="slot-machine-container">
          <p>No symbols available for the slot machine.</p>
          <p>Make sure users and characters have slot icons configured.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="slots-container">
      <h1>🎰 Slots</h1>
      
      <div className="slot-machine-container">
        <div className="slot-machine">
          <div className="slot-reels-container">
            {[0, 1, 2].map((reelIndex) => (
              <div 
                key={reelIndex}
                className={`${getReelClassName(reelIndex)} ${isWinning ? 'winning' : ''}`}
              >
                <div 
                  className="slot-reel-inner"
                  style={{ 
                    transform: getReelTransform(reelIndex)
                  }}
                >
                  {getReelSymbols(reelIndex).map((symbol, symbolIndex) => (
                    <div key={`${reelIndex}-${symbolIndex}`} className="slot-symbol">
                      {symbol.iconb64 ? (
                        <img 
                          src={`data:image/png;base64,${symbol.iconb64}`}
                          alt={symbol.displayName}
                        />
                      ) : (
                        <div className="slot-symbol-placeholder" />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Rarity Spinner */}
        <div className={`rarity-spinner-container ${raritySpinState.visible ? 'visible' : ''}`}>
          <div className="rarity-spinner">
            <div className="rarity-viewport">
              <div className={`rarity-reel ${raritySpinState.spinning ? 'spinning' : ''}`}>
                {raritySpinState.spinning ? (
                  // Show all rarities cycling for spinning animation
                  Array.from({ length: 8 }, (_, i) => {
                    const rarityIndex = i % rarityOptions.length;
                    const rarity = rarityOptions[rarityIndex];
                    return (
                      <div 
                        key={`spin-${i}`}
                        className="rarity-item"
                        style={{ color: rarity.color }}
                      >
                        {rarity.name}
                      </div>
                    );
                  })
                ) : (
                  // Show only the final result, properly centered
                  <div 
                    key={`result-${raritySpinState.result}`}
                    className="rarity-item rarity-item-final"
                    style={{ 
                      color: rarityOptions[raritySpinState.result]?.color || '#3498db'
                    }}
                  >
                    {rarityOptions[raritySpinState.result]?.name || 'Common'}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Hide spin button when winning and rarity spinner is visible */}
        {!(isWinning && raritySpinState.visible) && (
          <button 
            className="spin-button"
            onClick={handleSpin}
            disabled={spinState.spinning || symbols.current.length === 0}
          >
            {spinState.spinning ? 'SPINNING...' : 'SPIN'}
          </button>
        )}
      </div>
    </div>
  );
};

export default Slots;