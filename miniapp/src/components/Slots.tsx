import React, { useEffect, useCallback, useMemo, useRef, useState } from 'react';
import { TelegramUtils } from '../utils/telegram';
import { ApiService } from '../services/api';
import { useSlotsStore } from '../stores/useSlotsStore';
import { getIconObjectUrl } from '../lib/iconUrlCache';
import { RARITY_SEQUENCE, getRarityGradient, normalizeRarityName } from '../utils/rarityStyles';
import type { RarityName } from '../utils/rarityStyles';
import {
  computeRarityWheelTransforms,
  generateRarityWheelStrip,
  RARITY_WHEEL_BASE_DURATION_MS,
  RARITY_WHEEL_FINAL_SETTLE_DELAY_MS,
} from '../utils/rarityWheel';
import {
  SLOT_REEL_COUNT,
  SLOT_STRIP_REPEAT_MULTIPLIER,
  SLOT_BASE_SPIN_DURATION_MS,
  SLOT_SPIN_DURATION_STAGGER_MS,
  SLOT_STOPPING_LEAD_MS,
  computeSlotSpinTransforms,
  computeSlotStaticTransform,
} from '../utils/slotWheel';
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

type ReelState = 'idle' | 'spinning' | 'stopping' | 'stopped';

interface PendingWin {
  symbol: SlotSymbol;
  rarity: RarityName;
}

const INITIAL_RESULTS = Array.from({ length: SLOT_REEL_COUNT }, (_, index) => index);
const INITIAL_REEL_STATES: ReelState[] = Array.from(
  { length: SLOT_REEL_COUNT },
  () => 'idle' as ReelState
);


const Slots: React.FC<SlotsProps> = ({ symbols: providedSymbols, spins: userSpins, userId, chatId, initData, onSpinConsumed }) => {
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
  const setRarityWheelState = useSlotsStore((state) => state.setRarityWheelState);
  const setRarityWheelTimeout = useSlotsStore((state) => state.setRarityWheelTimeout);
  const clearRarityWheelTimeout = useSlotsStore((state) => state.clearRarityWheelTimeout);
  const resetRarityWheel = useSlotsStore((state) => state.resetRarityWheel);
  const pendingWinRef = useRef<PendingWin | null>(null);
  const rarityWheelSymbols = useMemo(() => generateRarityWheelStrip(), []);

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
            });
          });
        });

        const settleDelay = RARITY_WHEEL_BASE_DURATION_MS + RARITY_WHEEL_FINAL_SETTLE_DELAY_MS;
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
    return () => {
      clearReelTimeouts();
    };
  }, [clearReelTimeouts]);

  const stripSymbols = useMemo(() => {
    if (symbols.length === 0) {
      return [] as SlotSymbol[];
    }

    const repeated: SlotSymbol[] = [];
    const total = symbols.length * SLOT_STRIP_REPEAT_MULTIPLIER;

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

  const generateServerVerifiedResults = useCallback(async (): Promise<{ isWin: boolean; results: number[]; rarity: string | null }> => {
    const availableSymbols = symbols.length;

    if (availableSymbols === 0) {
      return { isWin: false, results: Array(SLOT_REEL_COUNT).fill(0), rarity: null };
    }

    const randomNumber = Math.floor(Math.random() * availableSymbols);

    const verifyResult = await ApiService.verifySlotSpin(
      userId,
      chatId,
      randomNumber,
      availableSymbols,
      initData
    );

    return {
      isWin: verifyResult.is_win,
      results: verifyResult.results,
      rarity: verifyResult.rarity ?? null
    };
  }, [userId, chatId, initData, symbols.length]);

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
    TelegramUtils.triggerHapticNotification('success');

    const completeVictory = async () => {
      try {
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
        return;
      }

      onSpinConsumed();

      const { results: finalResults, isWin, rarity: serverRarity } = await generateServerVerifiedResults();
      const normalizedResults = finalResults.slice(0, SLOT_REEL_COUNT);

      if (normalizedResults.length < SLOT_REEL_COUNT) {
        while (normalizedResults.length < SLOT_REEL_COUNT) {
          normalizedResults.push(0);
        }
      }

      setResults(normalizedResults);

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
        const stoppingTimeout = setTimeout(() => {
          setReelStates((prev) => {
            const next = [...prev];
            next[index] = 'stopping';
            return next;
          });
        }, Math.max(0, duration - SLOT_STOPPING_LEAD_MS));
        addReelTimeout(stoppingTimeout);

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

      if (isWin) {
        const winningIndex = normalizedResults[0];
        const winningSymbol = symbols[winningIndex];

        if (!winningSymbol) {
          console.warn('Winning symbol not found for index:', winningIndex);
        } else if (!serverRarity) {
          console.warn('Server did not supply rarity for winning spin');
        } else {
          const normalizedRarity = normalizeRarityName(serverRarity);
          if (!normalizedRarity) {
            console.warn('Server sent unsupported rarity for slots victory:', serverRarity);
          } else {
            pendingWinRef.current = { symbol: winningSymbol, rarity: normalizedRarity };
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
    onSpinConsumed,
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

  if (symbols.length === 0) {
    return (
      <div className="slots-container slots-container-loading" role="status" aria-live="polite">
        <h1>Loading...</h1>
      </div>
    );
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
                  transitionTimingFunction: 'cubic-bezier(0.32, 0.72, 0.15, 1)'
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
            <div className={`rarity-wheel-wrapper ${rarityWheelSpinning ? 'rarity-wheel-wrapper-spinning' : ''}`}>
              <div className="rarity-wheel-reel">
                <div
                  className="rarity-wheel-strip"
                  style={{
                    transform: `translateY(${rarityWheelTransform}px)`,
                    transitionDuration: `${rarityWheelDuration}ms`,
                    transitionTimingFunction: 'cubic-bezier(0.32, 0.72, 0.15, 1)'
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
                <div className="rarity-wheel-highlight" />
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
                    {userSpins.count === 0 && (
                      <div className="spins-refresh-hint">Spins refresh daily!</div>
                    )}
                  </div>
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