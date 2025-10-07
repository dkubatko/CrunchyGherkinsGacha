import React, { useEffect, useCallback, useMemo, useRef, useState } from 'react';
import { TelegramUtils } from '../utils/telegram';
import { ApiService } from '../services/api';
import { useSlotsStore } from '../stores/useSlotsStore';
import { getIconObjectUrl } from '../lib/iconUrlCache';
import { RARITY_SEQUENCE, getRarityColors, getRarityGradient, normalizeRarityName } from '../utils/rarityStyles';
import type { RarityName } from '../utils/rarityStyles';
import type { SlotSymbolInfo } from '../types';
import AppLoading from './AppLoading';
import {
  computeRarityWheelTransforms,
  generateRarityWheelStrip,
  RARITY_WHEEL_BASE_DURATION_MS,
  RARITY_WHEEL_TIMING_FUNCTION,
} from '../utils/rarityWheel';
import {
  SLOT_REEL_COUNT,
  SLOT_BASE_SPIN_DURATION_MS,
  SLOT_SPIN_DURATION_STAGGER_MS,
  SLOT_SPIN_TIMING_FUNCTION,
  computeSlotSpinTransforms,
  computeSlotStaticTransform,
  computeTotalSlotSymbols,
} from '../utils/slotWheel';
import './SlotMachine.css';

interface UserSpinsData {
  count: number;
  loading: boolean;
  error: string | null;
  nextRefreshTime?: string | null;
}

interface SlotsProps {
  symbols: SlotSymbol[];
  spins: UserSpinsData;
  userId: number;
  chatId: string;
  initData: string;
  refetchSpins: () => void;
  onSpinsUpdate: (count: number, nextRefreshTime?: string | null) => void;
}

interface SlotSymbol {
  id: number;
  iconb64?: string;
  displayName?: string;
  type: 'user' | 'character' | 'claim';
}

type ReelState = 'idle' | 'spinning' | 'stopped';

interface PendingWin {
  symbol: SlotSymbol;
  rarity: RarityName;
}

const INITIAL_RESULTS = Array.from({ length: SLOT_REEL_COUNT }, (_, index) => index);
const INITIAL_REEL_STATES: ReelState[] = Array.from(
  { length: SLOT_REEL_COUNT },
  () => 'idle' as ReelState
);

const clampAlpha = (value: number): number => Math.min(1, Math.max(0, value));

const formatTimeUntilRefresh = (nextRefreshTime: string | null | undefined): string => {
  if (!nextRefreshTime) {
    return 'Spins refresh daily!';
  }

  try {
    const now = new Date();
    const refreshDate = new Date(nextRefreshTime);
    const diffMs = refreshDate.getTime() - now.getTime();

    if (diffMs <= 0) {
      return 'Refresh available now!';
    }

    const diffMinutes = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMinutes / 60);
    const remainingMinutes = diffMinutes % 60;

    if (diffHours > 0) {
      return `Next refresh in ${diffHours}h ${remainingMinutes}m!`;
    } else {
      return `Next refresh in ${diffMinutes}m!`;
    }
  } catch {
    return 'Spins refresh daily!';
  }
};

const hexToRgba = (hex: string, alpha: number): string => {
  const normalized = hex.replace('#', '');
  const expanded =
    normalized.length === 3
      ? normalized
          .split('')
          .map((char) => `${char}${char}`)
          .join('')
      : normalized;

  if (expanded.length !== 6) {
    return hex;
  }

  const parsed = Number.parseInt(expanded, 16);
  if (Number.isNaN(parsed)) {
    return hex;
  }

  const r = (parsed >> 16) & 0xff;
  const g = (parsed >> 8) & 0xff;
  const b = parsed & 0xff;
  const clamped = clampAlpha(alpha);

  return `rgba(${r}, ${g}, ${b}, ${clamped})`;
};

const buildRarityHighlightVariables = (primary: string, secondary: string): Record<string, string> => ({
  '--rarity-highlight-border': secondary,
  '--rarity-highlight-shadow-inner': hexToRgba(secondary, 0.65),
  '--rarity-highlight-shadow-outer': hexToRgba(primary, 0.4),
  '--rarity-highlight-glow-inner': hexToRgba(secondary, 0.55),
  '--rarity-highlight-glow-mid': hexToRgba(primary, 0.35),
  '--rarity-wrapper-glow-inner': hexToRgba(secondary, 0.4),
  '--rarity-wrapper-glow-outer': hexToRgba(primary, 0.3),
});


const Slots: React.FC<SlotsProps> = ({ symbols: providedSymbols, spins: userSpins, userId, chatId, initData, refetchSpins, onSpinsUpdate }) => {
  const symbols = useSlotsStore((state) => state.symbols);
  const setSymbols = useSlotsStore((state) => state.setSymbols);
  const results = useSlotsStore((state) => state.results);
  const setResults = useSlotsStore((state) => state.setResults);
  const spinning = useSlotsStore((state) => state.spinning);
  const setSpinning = useSlotsStore((state) => state.setSpinning);
  const reelStates = useSlotsStore((state) => state.reelStates);
  const setReelStates = useSlotsStore((state) => state.setReelStates);
  const addReelTimeout = useSlotsStore((state) => state.addReelTimeout);
  const clearReelTimeouts = useSlotsStore((state) => state.clearReelTimeouts);

  const [stripTransforms, setStripTransforms] = useState<number[]>(Array(SLOT_REEL_COUNT).fill(0));
  const [stripDurations, setStripDurations] = useState<number[]>(Array(SLOT_REEL_COUNT).fill(0));
  const rarityWheelActive = useSlotsStore((state) => state.rarityWheelActive);
  const rarityWheelSpinning = useSlotsStore((state) => state.rarityWheelSpinning);
  const rarityWheelTransform = useSlotsStore((state) => state.rarityWheelTransform);
  const rarityWheelDuration = useSlotsStore((state) => state.rarityWheelDuration);
  const rarityWheelTarget = useSlotsStore((state) => state.rarityWheelTarget);
  const setRarityWheelState = useSlotsStore((state) => state.setRarityWheelState);
  const setRarityWheelTimeout = useSlotsStore((state) => state.setRarityWheelTimeout);
  const clearRarityWheelTimeout = useSlotsStore((state) => state.clearRarityWheelTimeout);
  const resetRarityWheel = useSlotsStore((state) => state.resetRarityWheel);
  const pendingWinRef = useRef<PendingWin | null>(null);
  const rarityWheelSymbols = useMemo(() => generateRarityWheelStrip(), []);
  const [imagesReady, setImagesReady] = useState(false);
  const [, setRefreshTick] = useState(0);

  const rarityHighlightVariables = useMemo<React.CSSProperties | undefined>(() => {
    if (!rarityWheelTarget) {
      return undefined;
    }

    const [primary, secondary] = getRarityColors(rarityWheelTarget);
    const variables = buildRarityHighlightVariables(primary, secondary);
    return variables as React.CSSProperties;
  }, [rarityWheelTarget]);

  const startRarityWheelAnimation = useCallback(
    (targetRarity: RarityName | null): Promise<void> | null => {
      if (!targetRarity) {
        return null;
      }

      const targetIndex = RARITY_SEQUENCE.findIndex((name) => name === targetRarity);
      if (targetIndex < 0) {
        return null;
      }

      clearRarityWheelTimeout();

      const { initial, final } = computeRarityWheelTransforms(targetIndex, RARITY_SEQUENCE.length);

      setRarityWheelState({
        rarityWheelActive: true,
        rarityWheelTarget: targetRarity,
        rarityWheelSpinning: true,
        rarityWheelTransform: initial,
        rarityWheelDuration: 0,
      });

      TelegramUtils.triggerHapticImpact('light');

      return new Promise<void>((resolve) => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            setRarityWheelState({
              rarityWheelDuration: RARITY_WHEEL_BASE_DURATION_MS,
              rarityWheelTransform: final,
              rarityWheelSpinning: true,
            });
          });
        });

        const settleDelay = RARITY_WHEEL_BASE_DURATION_MS;
        const timeout = setTimeout(() => {
          TelegramUtils.triggerHapticImpact('heavy');
          setRarityWheelState({
            rarityWheelSpinning: false,
            rarityWheelTransform: final,
            rarityWheelDuration: 0,
          });
          setRarityWheelTimeout(null);
          resolve();
        }, settleDelay);

        setRarityWheelTimeout(timeout);
      });
    },
    [clearRarityWheelTimeout, setRarityWheelState, setRarityWheelTimeout]
  );

  useEffect(() => {
    setSymbols(providedSymbols);
    const initialResults =
      providedSymbols.length >= SLOT_REEL_COUNT
        ? [...INITIAL_RESULTS]
        : Array(SLOT_REEL_COUNT).fill(0);
    setResults(initialResults);
    setReelStates([...INITIAL_REEL_STATES]);
  }, [providedSymbols, setSymbols, setResults, setReelStates]);

  useEffect(() => {
    const activeSymbols = symbols.length > 0 ? symbols : providedSymbols;

    if (typeof window === 'undefined') {
      setImagesReady(true);
      return;
    }

    if (activeSymbols.length === 0) {
      setImagesReady(true);
      return;
    }

    const uniqueIcons = Array.from(
      new Set(
        activeSymbols
          .map((symbol) => symbol.iconb64)
          .filter((icon): icon is string => Boolean(icon))
      )
    );

    if (uniqueIcons.length === 0) {
      setImagesReady(true);
      return;
    }

    let cancelled = false;
    let remaining = uniqueIcons.length;

    setImagesReady(false);

    const markDone = () => {
      if (cancelled) {
        return;
      }
      remaining -= 1;
      if (remaining <= 0) {
        const complete = () => {
          if (!cancelled) {
            setImagesReady(true);
          }
        };

        if (typeof window.requestAnimationFrame === 'function') {
          window.requestAnimationFrame(() => {
            if (!cancelled) {
              window.requestAnimationFrame(complete);
            }
          });
        } else {
          complete();
        }
      }
    };

    uniqueIcons.forEach((icon) => {
      const img = new Image();
      const objectUrl = getIconObjectUrl(icon);

      const handleComplete = () => {
        markDone();
      };

      img.addEventListener('load', async () => {
        try {
          await img.decode();
        } catch {
          // ignore decode failures, still treat as ready
        }
        handleComplete();
      });

      img.addEventListener('error', handleComplete);
      img.src = objectUrl;
    });

    return () => {
      cancelled = true;
    };
  }, [symbols, providedSymbols]);

  useEffect(() => {
    return () => {
      clearReelTimeouts();
    };
  }, [clearReelTimeouts]);

  // Update time display every minute when spins are at 0 and we have a refresh time
  useEffect(() => {
    if (userSpins.count === 0 && userSpins.nextRefreshTime) {
      const interval = setInterval(() => {
        setRefreshTick(tick => tick + 1);
      }, 60000); // Update every minute

      return () => clearInterval(interval);
    }
  }, [userSpins.count, userSpins.nextRefreshTime]);

  const stripSymbols = useMemo(() => {
    if (symbols.length === 0) {
      return [] as SlotSymbol[];
    }

    const repeated: SlotSymbol[] = [];
    const total = computeTotalSlotSymbols(symbols.length);

    for (let i = 0; i < total; i += 1) {
      repeated.push(symbols[i % symbols.length]);
    }

    return repeated;
  }, [symbols]);

  useEffect(() => {
    if (spinning || symbols.length === 0) {
      return;
    }

    const transforms = results
      .slice(0, SLOT_REEL_COUNT)
      .map((result) => computeSlotStaticTransform(result, symbols.length));
    setStripDurations(Array(SLOT_REEL_COUNT).fill(0));
    setStripTransforms(transforms);
  }, [results, symbols.length, spinning]);

  const generateServerVerifiedResults = useCallback(async (): Promise<{ 
    isWin: boolean;
    slotResults: SlotSymbolInfo[];
    rarity: string | null;
  }> => {
    const availableSymbols = symbols.length;

    if (availableSymbols === 0) {
      return { isWin: false, slotResults: [], rarity: null };
    }

    const randomNumber = Math.floor(Math.random() * availableSymbols);

    // Send the full symbol list to the server
    const symbolsInfo = symbols.map(s => ({ id: s.id, type: s.type }));

    const verifyResult = await ApiService.verifySlotSpin(
      userId,
      chatId,
      randomNumber,
      symbolsInfo,
      initData
    );

    return {
      isWin: verifyResult.is_win,
      slotResults: verifyResult.slot_results,
      rarity: verifyResult.rarity ?? null
    };
  }, [userId, chatId, initData, symbols]);

  const finalizeSpin = useCallback(() => {
    const pendingWin = pendingWinRef.current;
    pendingWinRef.current = null;

    const resetReels = () => {
      setReelStates([...INITIAL_REEL_STATES]);
      setSpinning(false);
      resetRarityWheel();
    };

    if (!pendingWin) {
      TelegramUtils.triggerHapticNotification('error');
      resetReels();
      return;
    }

    const { symbol, rarity } = pendingWin;
    
    // Check if this is a claim win (special handling)
    if (symbol.type === 'claim') {
      TelegramUtils.triggerHapticNotification('success');
      
      const processClaimWin = async () => {
        try {
          await new Promise<void>((resolve) => setTimeout(resolve, 1000));
          
          const claimAmount = 1;
          const result = await ApiService.processClaimWin(userId, chatId, claimAmount, initData);
          
          const pointsText = claimAmount === 1 ? 'claim point' : 'claim points';
          const message = `Won ${claimAmount} ${pointsText}!\n\nBalance: ${result.balance}`;
          TelegramUtils.showAlert(message);
          TelegramUtils.triggerHapticNotification('success');
        } catch (error) {
          console.error('Failed to process claim win:', error);
          const errorMessage = error instanceof Error ? error.message : 'Failed to process claim win';
          TelegramUtils.showAlert(`Error: ${errorMessage}`);
        } finally {
          resetReels();
        }
      };
      
      processClaimWin();
      return;
    }

    // Card win - existing logic
    TelegramUtils.triggerHapticNotification('success');

    const completeVictory = async () => {
      try {
        await new Promise<void>((resolve) => setTimeout(resolve, 1000));
        await ApiService.processSlotsVictory(
          userId,
          chatId,
          rarity.toLowerCase(),
          symbol.id,
          symbol.type,
          initData
        );

        TelegramUtils.showAlert(`Won ${rarity} ${symbol.displayName || 'Unknown'}!\n\nGenerating card...`);
        setTimeout(() => {
          TelegramUtils.closeApp();
        }, 400);
      } catch (error) {
        console.error('Failed to process slots victory:', error);
        const errorMessage = error instanceof Error ? error.message : 'Failed to process victory';
        TelegramUtils.showAlert(`Error: ${errorMessage}`);
      } finally {
        resetReels();
      }
    };

    const animation = startRarityWheelAnimation(rarity);
    if (animation) {
      animation.then(completeVictory).catch(() => {
        completeVictory();
      });
    } else {
      completeVictory();
    }
  }, [chatId, initData, resetRarityWheel, setReelStates, setSpinning, startRarityWheelAnimation, userId]);

  const handleSpin = useCallback(async () => {
    if (spinning || symbols.length === 0 || userSpins.loading) {
      return;
    }

    if (userSpins.count <= 0) {
      TelegramUtils.showAlert('No spins available! Spins refresh daily.');
      return;
    }

    TelegramUtils.triggerHapticImpact('medium');

    resetRarityWheel();
    setSpinning(true);
    setReelStates(Array.from({ length: SLOT_REEL_COUNT }, () => 'spinning' as ReelState));
    clearReelTimeouts();
    pendingWinRef.current = null;

    try {
      const consumeResult = await ApiService.consumeUserSpin(userId, chatId, initData);

      if (!consumeResult.success) {
        const message = consumeResult.message || 'Failed to consume spin';
        TelegramUtils.showAlert(message);
        setSpinning(false);
        setReelStates([...INITIAL_REEL_STATES]);
        // Update spin count from server response without refetching
        if (consumeResult.spins_remaining !== undefined) {
          onSpinsUpdate(consumeResult.spins_remaining);
        } else {
          refetchSpins();
        }
        return;
      }

      // Update spin count from server response without refetching
      if (consumeResult.spins_remaining !== undefined) {
        onSpinsUpdate(consumeResult.spins_remaining);
      } else {
        refetchSpins();
      }

      const { isWin, slotResults, rarity: serverRarity } = await generateServerVerifiedResults();
      
      // Convert server-provided symbol results to indices
      const normalizedResults = slotResults.map(symbolInfo => {
        const index = symbols.findIndex(s => s.id === symbolInfo.id && s.type === symbolInfo.type);
        return index !== -1 ? index : 0; // Fallback to 0 if symbol not found
      });

      // Ensure we have exactly 3 results
      while (normalizedResults.length < SLOT_REEL_COUNT) {
        normalizedResults.push(0);
      }

      setResults(normalizedResults.slice(0, SLOT_REEL_COUNT));

      const spinTransforms = normalizedResults.map((result) =>
        computeSlotSpinTransforms(result, symbols.length)
      );
      const finalTransforms = spinTransforms.map((value) => value.final);
      const initialTransforms = spinTransforms.map((value) => value.initial);
      const durations = normalizedResults.map(
        (_, index) => SLOT_BASE_SPIN_DURATION_MS + index * SLOT_SPIN_DURATION_STAGGER_MS
      );

      setStripDurations(Array(SLOT_REEL_COUNT).fill(0));
      setStripTransforms(initialTransforms);

      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setStripDurations(durations);
          setStripTransforms(finalTransforms);
        });
      });

      durations.forEach((duration, index) => {
        const finalTimeout = setTimeout(() => {
          setReelStates((prev) => {
            const next = [...prev];
            next[index] = 'stopped';
            return next;
          });

          TelegramUtils.triggerHapticImpact('medium');

          if (index === SLOT_REEL_COUNT - 1) {
            finalizeSpin();
          }
        }, duration);
        addReelTimeout(finalTimeout);
      });

      if (isWin && slotResults.length > 0) {
        const winningSymbolInfo = slotResults[0];
        
        if (winningSymbolInfo.type === 'claim') {
          // Claim win - find the claim symbol and set it with a dummy rarity
          const winningIndex = normalizedResults[0];
          const winningSymbolFromArray = symbols[winningIndex];

          if (!winningSymbolFromArray) {
            console.warn('Winning claim symbol not found for index:', winningIndex);
          } else {
            // Use 'Common' as a placeholder rarity for claim wins (won't be used)
            pendingWinRef.current = { 
              symbol: winningSymbolFromArray, 
              rarity: 'Common' as RarityName 
            };
          }
        } else if (serverRarity) {
          // Card win - process victory
          const winningIndex = normalizedResults[0];
          const winningSymbolFromArray = symbols[winningIndex];

          if (!winningSymbolFromArray) {
            console.warn('Winning symbol not found for index:', winningIndex);
          } else {
            const normalizedRarity = normalizeRarityName(serverRarity);
            if (!normalizedRarity) {
              console.warn('Server sent unsupported rarity for slots victory:', serverRarity);
            } else {
              pendingWinRef.current = { symbol: winningSymbolFromArray, rarity: normalizedRarity };
            }
          }
        }
      }
    } catch (error) {
      console.error('Failed to spin slots:', error);
      const errorMessage = error instanceof Error ? error.message : 'Failed to process spin';
      TelegramUtils.showAlert(errorMessage);
      setStripDurations(Array(SLOT_REEL_COUNT).fill(0));
      setStripTransforms(Array(SLOT_REEL_COUNT).fill(0));
      setReelStates([...INITIAL_REEL_STATES]);
      setSpinning(false);
    }
  }, [
    spinning,
    symbols,
    userSpins,
    userId,
    chatId,
    initData,
    refetchSpins,
    onSpinsUpdate,
    clearReelTimeouts,
    setReelStates,
    generateServerVerifiedResults,
    setResults,
    addReelTimeout,
    finalizeSpin,
    setSpinning,
    resetRarityWheel
  ]);

  const isWinning = useMemo(() => {
    if (symbols.length === 0) {
      return false;
    }
    const hasMatchingResults =
      results.length === SLOT_REEL_COUNT && results.every((value) => value === results[0]);
    const reelsStopped = reelStates.every((state) => state === 'stopped');
    return hasMatchingResults && reelsStopped;
  }, [results, reelStates, symbols.length]);

  if (!imagesReady) {
    return <AppLoading />;
  }

  return (
    <div className="slots-container">
      <h1>🎰 Slots</h1>

      <div className="slot-machine-container">
        <div className={`slot-reels ${isWinning ? 'slot-reels-winning' : ''}`}>
          {Array.from({ length: SLOT_REEL_COUNT }, (_, reelIndex) => reelIndex).map((reelIndex) => (
            <div
              key={`reel-${reelIndex}`}
              className={`slot-reel reel-${reelIndex} state-${reelStates[reelIndex]}`}
            >
              <div
                className="slot-reel-strip"
                style={{
                  transform: `translateY(${stripTransforms[reelIndex]}px)`,
                  transitionDuration: `${stripDurations[reelIndex]}ms`,
                  transitionTimingFunction: SLOT_SPIN_TIMING_FUNCTION
                }}
              >
                {stripSymbols.map((symbol, symbolIndex) => (
                  <div key={`reel-${reelIndex}-symbol-${symbolIndex}`} className="slot-cell">
                    {symbol.iconb64 ? (
                      <img
                        src={getIconObjectUrl(symbol.iconb64)}
                        alt={symbol.displayName}
                        decoding="async"
                      />
                    ) : (
                      <div className="slot-symbol-placeholder" />
                    )}
                  </div>
                ))}
              </div>
              <div className="slot-highlight" />
            </div>
          ))}
        </div>

        <div className="slot-controls-area">
          {rarityWheelActive ? (
            <div
              className={`rarity-wheel-wrapper ${
                rarityWheelSpinning ? 'rarity-wheel-wrapper-spinning' : 'rarity-wheel-wrapper-final'
              }`}
              style={rarityHighlightVariables}
            >
              <div className="rarity-wheel-reel">
                <div
                  className="rarity-wheel-strip"
                  style={{
                    transform: `translateY(${rarityWheelTransform}px)`,
                    transitionDuration: `${rarityWheelDuration}ms`,
                    transitionTimingFunction: RARITY_WHEEL_TIMING_FUNCTION
                  }}
                >
                  {rarityWheelSymbols.map((rarityName, index) => (
                    <div key={`rarity-strip-${index}`} className="rarity-wheel-cell">
                      <span
                        className="rarity-wheel-label"
                        style={{
                          background: getRarityGradient(rarityName),
                          WebkitBackgroundClip: 'text',
                          WebkitTextFillColor: 'transparent',
                          backgroundClip: 'text'
                        }}
                      >
                        {rarityName}
                      </span>
                    </div>
                  ))}
                </div>
                <div
                  className={`rarity-wheel-highlight ${
                    rarityWheelSpinning ? '' : 'rarity-wheel-highlight-final'
                  }`}
                />
              </div>
            </div>
          ) : (
            <>
              <button
                className="spin-button"
                onClick={handleSpin}
                disabled={spinning || symbols.length === 0 || userSpins.loading || userSpins.count <= 0}
              >
                {spinning ? 'SPINNING…' : 'SPIN'}
              </button>

              <div className="spins-container">
                {userSpins.error ? (
                  <div className="spins-display error">
                    <div className="spins-icon">⚠️</div>
                    <div className="spins-text">
                      <span className="spins-count">?</span>
                      <span className="spins-label">Error loading spins</span>
                    </div>
                  </div>
                ) : (
                  <div className="spins-display">
                    <div className="spins-text">
                      <div className="spins-count-row">
                        <div className="spins-coin" aria-hidden="true" />
                        <span className="spins-count">{userSpins.count}</span>
                      </div>
                      <span className="spins-label">Spins Available</span>
                    </div>
                  </div>
                )}
                {userSpins.count === 0 && !userSpins.error && (
                  <div className="spins-refresh-hint">{formatTimeUntilRefresh(userSpins.nextRefreshTime)}</div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Slots;