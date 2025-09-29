import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { TelegramUtils } from '../utils/telegram';
import { ApiService } from '../services/api';
import './SlotMachine.css';

interface UserSpinsData {
  count: number;
  loading: boolean;
  error: string | null;
}

interface SlotsProps {
  symbols: SlotSymbol[];
  spins: UserSpinsData;
  userId: number;
  chatId: string;
  initData: string;
  onSpinConsumed: () => void;
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

const Slots: React.FC<SlotsProps> = ({ symbols: providedSymbols, spins: userSpins, userId, chatId, initData, onSpinConsumed }) => {
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

  
  const symbols = useRef<SlotSymbol[]>(providedSymbols);
  const reelTimeouts = useRef<NodeJS.Timeout[]>([]);
  const rarityTimeouts = useRef<NodeJS.Timeout[]>([]);
  
  const rarityOptions = useMemo(() => [
    { name: 'Common', color: '#3498db', emoji: '⚪' }, // Blue
    { name: 'Rare', color: '#2ecc71', emoji: '🟢' },   // Green
    { name: 'Epic', color: '#9b59b6', emoji: '🟣' },   // Purple
    { name: 'Legendary', color: '#f39c12', emoji: '🟡' } // Gold
  ], []);

    // Update symbols when providedSymbols change
  useEffect(() => {
    symbols.current = providedSymbols;
    
    // Set initial results to show the first 3 different symbols if available
    const initialResults = providedSymbols.length >= 3 
      ? [0, 1, 2] 
      : [0, 0, 0];
      
    setSpinState(prev => ({
      ...prev,
      results: initialResults
    }));
  }, [providedSymbols]);



  // Cleanup function to prevent memory leaks  
  useEffect(() => {
    return () => {
      reelTimeouts.current.forEach(timeout => clearTimeout(timeout));
      reelTimeouts.current = [];
      rarityTimeouts.current.forEach(timeout => clearTimeout(timeout));
      rarityTimeouts.current = [];
    };
  }, []);

  const generateRandomResults = (): number[] => {
    const availableSymbols = symbols.current.length;
    if (availableSymbols === 0) return [0, 0, 0];

    // 2% chance to win
    const isWin = Math.random() < 0.02;
    
    if (isWin) {
      // All three reels show the same symbol
      const winningSymbol = Math.floor(Math.random() * availableSymbols);
      return [winningSymbol, winningSymbol, winningSymbol];
    } else {
      // Ensure it's a loss - at least one reel must be different
      const firstSymbol = Math.floor(Math.random() * availableSymbols);
      const secondSymbol = Math.floor(Math.random() * availableSymbols);
      let thirdSymbol = Math.floor(Math.random() * availableSymbols);
      
      // If by chance all three are the same, force the third to be different
      if (firstSymbol === secondSymbol && secondSymbol === thirdSymbol && availableSymbols > 1) {
        thirdSymbol = (thirdSymbol + 1) % availableSymbols;
      }
      
      return [firstSymbol, secondSymbol, thirdSymbol];
    }
  };

  const startRaritySpinner = useCallback(async (winningResultIndex: number) => {
    // Clear any existing rarity timeouts
    rarityTimeouts.current.forEach(timeout => clearTimeout(timeout));
    rarityTimeouts.current = [];

    // Generate weighted random result (more common rarities have higher chance)
    const weights = [55, 25, 15, 5]; // Common, Rare, Epic, Legendary
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

    // Haptic feedback when rarity spinner starts
    TelegramUtils.triggerHapticImpact('heavy');

    // Spin for 2 seconds, then process the victory
    const stopSpinTimeout = setTimeout(async () => {
      // First stop the fast spinning animation
      setRaritySpinState(prev => ({
        ...prev,
        spinning: false
      }));

      // Haptic feedback when rarity is revealed
      TelegramUtils.triggerHapticNotification('success');
      
      // After a brief moment, process the victory
      const processVictoryTimeout = setTimeout(async () => {
        const winningSymbol = symbols.current[winningResultIndex];
        const rarity = rarityOptions[result].name;
        const winnerName = winningSymbol?.displayName || 'Unknown';
        
        try {
          // Call the API to process the slots victory
          await ApiService.processSlotsVictory(
            userId,
            chatId,
            rarity.toLowerCase(), // API expects lowercase rarity
            winningSymbol.id,
            winningSymbol.type,
            initData
          );
          
          // If API call successful, show win notification and close app
          TelegramUtils.showAlert(`Won ${rarity} ${winnerName}!\n\nGenerating card...`);
          
          // Close the miniapp after showing the alert
          setTimeout(() => {
            TelegramUtils.closeApp();
          }, 100);
          
        } catch (error) {
          console.error('Failed to process slots victory:', error);
          
          // Show error alert
          const errorMessage = error instanceof Error ? error.message : 'Failed to process victory';
          TelegramUtils.showAlert(`Error: ${errorMessage}`);
          
          // Reset slot state to allow retry
          setSpinState({
            spinning: false,
            reelStates: ['idle', 'idle', 'idle'],
            results: providedSymbols.length >= 3 ? [0, 1, 2] : [0, 0, 0]
          });
          
          // Hide rarity spinner
          setRaritySpinState({
            visible: false,
            spinning: false,
            result: 0
          });
        }
      }, 500);
      
      rarityTimeouts.current.push(processVictoryTimeout);
    }, 2000);

    rarityTimeouts.current.push(stopSpinTimeout);
  }, [rarityOptions, providedSymbols, userId, chatId, initData]);

  const stopReel = useCallback((reelIndex: number, finalResult: number) => {
    // Haptic feedback when reel starts to slow down
    TelegramUtils.triggerHapticImpact('medium');

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
        const isWin = allStopped && prev.results[0] === prev.results[1] && prev.results[1] === prev.results[2];
        
        if (isWin) {
          // Haptic feedback for winning combination
          TelegramUtils.triggerHapticNotification('success');
          // Use setTimeout to ensure state update happens first
          setTimeout(() => startRaritySpinner(prev.results[0]), 0);
        } else if (allStopped) {
          // Haptic feedback for losing combination
          TelegramUtils.triggerHapticNotification('error');
        }
        
        return {
          ...prev,
          reelStates: newReelStates
          // Don't change spinning here - it's already false
        };
      });
    }, 300);
  }, [startRaritySpinner]);

  const handleSpin = useCallback(async () => {
    if (spinState.spinning || symbols.current.length === 0 || userSpins.loading) return;

    // Check if user has spins available
    if (userSpins.count <= 0) {
      TelegramUtils.showAlert('No spins available! Spins refresh daily.');
      return;
    }

    try {
      // Attempt to consume a spin first
      const consumeResult = await ApiService.consumeUserSpin(userId, chatId, initData);
      
      if (!consumeResult.success) {
        // Show server error message if available, otherwise default message
        const message = consumeResult.message || 'Failed to consume spin';
        TelegramUtils.showAlert(message);
        return;
      }

      // Notify parent that a spin was consumed
      onSpinConsumed();

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

      // Haptic feedback when spin starts
      TelegramUtils.triggerHapticImpact('light');

      // Stop reels with staggered timing (left to right)
      [0, 1, 2].forEach((reelIndex) => {
        const timeout = setTimeout(() => {
          stopReel(reelIndex, finalResults[reelIndex]);
        }, 1000 + reelIndex * 300); // 1s base + 300ms stagger per reel

        reelTimeouts.current.push(timeout);
      });

    } catch (error) {
      console.error('Failed to consume spin:', error);
      const errorMessage = error instanceof Error ? error.message : 'Failed to process spin';
      TelegramUtils.showAlert(errorMessage);
    }
  }, [spinState.spinning, userSpins.count, userSpins.loading, stopReel, userId, chatId, initData, onSpinConsumed]);

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
            disabled={spinState.spinning || symbols.current.length === 0 || userSpins.loading || userSpins.count <= 0}
          >
            {spinState.spinning ? 'SPINNING...' : 'SPIN'}
          </button>
        )}

        {/* Spins Counter */}
        <div className="spins-container">
          {userSpins.loading ? (
            <div className="spins-display loading">
              <div className="spins-icon">🎰</div>
              <div className="spins-text">
                <span>Loading spins...</span>
              </div>
            </div>
          ) : userSpins.error ? (
            <div className="spins-display error">
              <div className="spins-icon">⚠️</div>
              <div className="spins-text">
                <span>Error loading spins</span>
              </div>
            </div>
          ) : (
            <div className="spins-display">
              <div className="spins-icon">✨</div>
              <div className="spins-text">
                <span className="spins-count">{userSpins.count}</span>
                <span className="spins-label">Spins Available</span>
              </div>
              {userSpins.count === 0 && (
                <div className="spins-refresh-hint">
                  Spins refresh daily!
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Slots;