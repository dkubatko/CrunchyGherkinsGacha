import React, { useEffect, useCallback, useMemo, useRef, useState } from 'react';
import { TelegramUtils } from '@/utils/telegram';
import { ApiService } from '@/services/api';
import { useSlotsStore } from '@/stores/useSlotsStore';
import { getIconObjectUrl } from '@/lib/iconUrlCache';
import { SLOT_RARITY_SEQUENCE, getRarityColors, getRarityGradient, normalizeRarityName } from '@/utils/rarityStyles';
import type { RarityName } from '@/utils/rarityStyles';
import type { SlotSymbolInfo, SlotSymbolSummary } from '@/types';
import { Title, SpinsBadge, ClaimPointsBadge } from '@/components/common';
import {
  computeRarityWheelTransforms,
  generateRarityWheelStrip,
  RARITY_WHEEL_BASE_DURATION_MS,
  RARITY_WHEEL_TIMING_FUNCTION,
} from '@/utils/rarityWheel';
import {
  SLOT_REEL_COUNT,
  SLOT_BASE_SPIN_DURATION_MS,
  SLOT_SPIN_DURATION_STAGGER_MS,
  SLOT_SPIN_TIMING_FUNCTION,
  computeSlotSpinTransforms,
  computeSlotStaticTransform,
  computeTotalSlotSymbols,
} from '@/utils/slotWheel';
import './SlotMachine.css';
import '../Casino.css';

interface UserSpinsData {
  count: number;
  loading: boolean;
  error: string | null;
}

interface MegaspinData {
  spinsUntilMegaspin: number;
  totalSpinsRequired: number;
  megaspinAvailable: boolean;
  loading: boolean;
  error: string | null;
}

interface MegaspinInfo {
  spins_until_megaspin: number;
  total_spins_required: number;
  megaspin_available: boolean;
}

interface SlotsProps {
  symbols: SlotSymbol[];
  spins: UserSpinsData;
  megaspin: MegaspinData;
  userId: number;
  chatId: string;
  initData: string;
  onSpinsUpdate: (count: number) => void;
  onMegaspinUpdate: (megaspinInfo: MegaspinInfo) => void;
  claimPoints?: number;
  onClaimPointsUpdate?: (count: number) => void;
}

interface SlotSymbol {
  id: number;
  iconb64?: string;
  displayName?: string;
  type: 'user' | 'character' | 'claim' | 'set';
}

type ReelState = 'idle' | 'spinning' | 'stopped';

interface PendingWin {
  symbol: SlotSymbol;
  rarity: RarityName;
  winType: 'card' | 'aspect' | 'claim';
  setId?: number | null;
  setName?: string | null;
  spinResultId?: string | null;
}

const INITIAL_REEL_STATES: ReelState[] = Array.from(
  { length: SLOT_REEL_COUNT },
  () => 'idle' as ReelState
);

const SLOT_BET_MULTIPLIERS = [1, 5, 10] as const;
type SlotBetMultiplier = (typeof SLOT_BET_MULTIPLIERS)[number];

const clampAlpha = (value: number): number => Math.min(1, Math.max(0, value));

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


const Slots: React.FC<SlotsProps> = ({ symbols: providedSymbols, spins: userSpins, megaspin: megaspinData, userId, chatId, initData, onSpinsUpdate, onMegaspinUpdate, claimPoints, onClaimPointsUpdate }) => {
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
  const [isMegaspinning, setIsMegaspinning] = useState(false);
  const longPressTimerRef = useRef<NodeJS.Timeout | null>(null);
  const longPressTriggeredRef = useRef(false);
  
  // Speed multipliers for spin animations
  const REGULAR_SPEED_MULTIPLIER = 1.5;
  const AUTOSPIN_SPEED_MULTIPLIER = 2;
  const getSpeedMultiplier = useCallback(() => 
    isAutospinningRef.current ? AUTOSPIN_SPEED_MULTIPLIER : REGULAR_SPEED_MULTIPLIER
  , []);
  const [isAutospinMode, setIsAutospinMode] = useState(false);
  const [isAutospinning, setIsAutospinning] = useState(false);
  const [isAutospinStopping, setIsAutospinStopping] = useState(false);
  const autospinStopRef = useRef(false);
  const isAutospinningRef = useRef(false);
  
  // Autospin win tracking
  const autospinCardsWonRef = useRef(0);
  const autospinAspectsWonRef = useRef(0);
  const autospinClaimPointsWonRef = useRef(0);

  // Bet multiplier (1x default; 5x and 10x multiply per-bet win chance).
  // The server is the source of truth — this state only drives UI and
  // the value passed to `/slots/spin`. We snapshot it at spin start so a
  // mid-flight change can't desync the in-flight animation.
  const [selectedMultiplier, setSelectedMultiplier] = useState<SlotBetMultiplier>(1);
  const activeMultiplierRef = useRef<SlotBetMultiplier>(1);

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

      const targetIndex = SLOT_RARITY_SEQUENCE.findIndex((name) => name === targetRarity);
      if (targetIndex < 0) {
        return null;
      }

      clearRarityWheelTimeout();

      const { initial, final } = computeRarityWheelTransforms(targetIndex, SLOT_RARITY_SEQUENCE.length);

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
              rarityWheelDuration: RARITY_WHEEL_BASE_DURATION_MS / getSpeedMultiplier(),
              rarityWheelTransform: final,
              rarityWheelSpinning: true,
            });
          });
        });

        const settleDelay = RARITY_WHEEL_BASE_DURATION_MS / getSpeedMultiplier();
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
    [clearRarityWheelTimeout, setRarityWheelState, setRarityWheelTimeout, getSpeedMultiplier]
  );

  useEffect(() => {
    setSymbols(providedSymbols);
    const initialResults =
      providedSymbols.length >= SLOT_REEL_COUNT
        ? Array.from({ length: SLOT_REEL_COUNT }, () =>
            Math.floor(Math.random() * providedSymbols.length)
          )
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

  // Server returns slot_results (id+type triple) and optionally a full
  // SlotSymbolSummary for the winning symbol. The local symbol pool may
  // be stale (e.g. a new user/character/set was added between the
  // initial pool fetch and this spin), so we merge any missing winning
  // symbol into the pool before computing animation indices. This
  // eliminates the prior "fall back to reel index 0" race that silently
  // mis-rendered legitimate wins.
  const resolveWinningSymbols = useCallback((
    slotResults: SlotSymbolInfo[],
    winningSymbol: SlotSymbolSummary | null | undefined,
  ): { symbols: SlotSymbol[]; indices: number[] } => {
    let pool = symbols;
    const lookup = (info: SlotSymbolInfo) =>
      pool.findIndex((s) => s.id === info.id && s.type === info.type);

    // Inject the winning symbol if it isn't in the local pool yet.
    if (winningSymbol && lookup(winningSymbol) === -1) {
      const injected: SlotSymbol = {
        id: winningSymbol.id,
        type: winningSymbol.type,
        displayName: winningSymbol.display_name ?? undefined,
        iconb64: winningSymbol.slot_icon_b64 ?? undefined,
      };
      pool = [...pool, injected];
      setSymbols(pool);
    }

    const indices = slotResults.map((info) => {
      const idx = lookup(info);
      if (idx !== -1) return idx;
      console.warn('Slot symbol missing from local pool', info);
      return 0;
    });
    return { symbols: pool, indices };
  }, [symbols, setSymbols]);

  const finalizeSpin = useCallback(() => {
    const pendingWin = pendingWinRef.current;
    pendingWinRef.current = null;
    const currentlyAutospinning = isAutospinningRef.current;

    const resetReels = () => {
      setReelStates([...INITIAL_REEL_STATES]);
      setSpinning(false);
      setIsMegaspinning(false);
      resetRarityWheel();
    };

    if (!pendingWin) {
      if (!currentlyAutospinning) {
        TelegramUtils.triggerHapticNotification('error');
      }
      resetReels();
      return;
    }

    const { symbol, rarity, winType, setName, spinResultId } = pendingWin;

    TelegramUtils.triggerHapticNotification('success');

    // Claim wins are synchronous — no rarity wheel animation
    if (winType === 'claim') {
      const processClaimWin = async () => {
        try {
          const delay = currentlyAutospinning ? 800 : 500;
          await new Promise<void>((resolve) => setTimeout(resolve, delay));
          
          const result = await ApiService.processClaimWin(userId, chatId, initData);
          
          if (onClaimPointsUpdate) {
            onClaimPointsUpdate(result.balance);
          }
          
          if (currentlyAutospinning) {
            autospinClaimPointsWonRef.current += 1;
          } else {
            TelegramUtils.showAlert(`Won 1 claim point!\n\nBalance: ${result.balance}`);
            TelegramUtils.triggerHapticNotification('success');
          }
        } catch (error) {
          console.error('Failed to process claim win:', error);
          if (!currentlyAutospinning) {
            const errorMessage = error instanceof Error ? error.message : 'Failed to process claim win';
            TelegramUtils.showAlert(`Error: ${errorMessage}`);
          }
        } finally {
          resetReels();
        }
      };
      
      processClaimWin();
      return;
    }

    // Card and aspect wins — fire-and-forget via unified victory endpoint
    const processVictory = async () => {
      try {
        const delay = currentlyAutospinning ? 800 : 500;
        await new Promise<void>((resolve) => setTimeout(resolve, delay));

        if (!spinResultId) {
          throw new Error('Missing spin result token');
        }

        await ApiService.processVictory(userId, chatId, spinResultId, initData);

        if (currentlyAutospinning) {
          if (winType === 'aspect') {
            autospinAspectsWonRef.current += 1;
          } else {
            autospinCardsWonRef.current += 1;
          }
        } else if (winType === 'aspect') {
          TelegramUtils.showAlert(`Won a ${rarity} ${setName ? setName + ' ' : ''}aspect!\n\nGenerating sphere...`);
        } else {
          TelegramUtils.showAlert(`Won ${rarity} ${symbol.displayName || 'Unknown'}!\n\nGenerating card...`);
        }
      } catch (error) {
        console.error('Failed to process slots victory:', error);
        if (!currentlyAutospinning) {
          const errorMessage = error instanceof Error ? error.message : 'Failed to process victory';
          TelegramUtils.showAlert(`Error: ${errorMessage}`);
        }
      } finally {
        resetReels();
      }
    };

    const animation = startRarityWheelAnimation(rarity);
    if (animation) {
      animation.then(processVictory).catch(() => processVictory());
    } else {
      processVictory();
    }
  }, [chatId, initData, isMegaspinning, onClaimPointsUpdate, resetRarityWheel, setReelStates, setSpinning, startRarityWheelAnimation, userId]);

  const handleSpin = useCallback(async (): Promise<boolean> => {
    // Ignore click if it was a long press that just completed
    if (longPressTriggeredRef.current) {
      return false;
    }

    if (spinning || symbols.length === 0 || userSpins.loading) {
      return false;
    }

    const multiplier = selectedMultiplier;

    if (userSpins.count < multiplier) {
      if (!isAutospinningRef.current) {
        TelegramUtils.showAlert(
          multiplier === 1
            ? 'No spins available! Spins refresh daily.'
            : `Not enough spins for a ${multiplier}x bet (need ${multiplier}).`
        );
      }
      // Return false without error - autospin loop will handle showing summary
      return false;
    }

    TelegramUtils.triggerHapticImpact('medium');

    activeMultiplierRef.current = multiplier;
    resetRarityWheel();
    setSpinning(true);
    setReelStates(Array.from({ length: SLOT_REEL_COUNT }, () => 'spinning' as ReelState));
    clearReelTimeouts();
    pendingWinRef.current = null;

    try {
      const spinResult = await ApiService.spin(userId, chatId, multiplier, initData);

      if (!spinResult.success) {
        const message = spinResult.message || 'Failed to spin';
        if (!isAutospinningRef.current) {
          TelegramUtils.showAlert(message);
        }
        setSpinning(false);
        setReelStates([...INITIAL_REEL_STATES]);
        onSpinsUpdate(spinResult.spins_remaining);
        if (spinResult.megaspin) {
          onMegaspinUpdate(spinResult.megaspin);
        }
        return false;
      }

      // Update balances from server response
      onSpinsUpdate(spinResult.spins_remaining);
      if (spinResult.megaspin) {
        onMegaspinUpdate(spinResult.megaspin);
      }

      const isWin = spinResult.is_win;
      const slotResults = spinResult.slot_results;
      const serverRarity = spinResult.rarity ?? null;
      const winType = spinResult.win_type ?? null;
      const setId = spinResult.set_id ?? null;
      const setName = spinResult.set_name ?? null;
      const spinResultId = spinResult.spin_result_id ?? null;

      // Resolve winning symbol against the local pool, injecting a
      // server-provided full payload if the pool is stale.
      const { symbols: effectiveSymbols, indices: rawIndices } = resolveWinningSymbols(
        slotResults,
        spinResult.winning_symbol,
      );
      const normalizedResults = [...rawIndices];

      // Ensure we have exactly 3 results
      while (normalizedResults.length < SLOT_REEL_COUNT) {
        normalizedResults.push(0);
      }

      setResults(normalizedResults.slice(0, SLOT_REEL_COUNT));

      const spinTransforms = normalizedResults.map((result) =>
        computeSlotSpinTransforms(result, effectiveSymbols.length)
      );
      const finalTransforms = spinTransforms.map((value) => value.final);
      const initialTransforms = spinTransforms.map((value) => value.initial);
      const speedMultiplier = getSpeedMultiplier();
      const durations = normalizedResults.map(
        (_, index) => (SLOT_BASE_SPIN_DURATION_MS + index * SLOT_SPIN_DURATION_STAGGER_MS) / speedMultiplier
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
        const winningIndex = normalizedResults[0];
        const winningSymbolFromArray = effectiveSymbols[winningIndex];

        if (!winningSymbolFromArray) {
          console.warn('Winning symbol not found for index:', winningIndex);
        } else if (winType === 'claim') {
          pendingWinRef.current = {
            symbol: winningSymbolFromArray,
            rarity: 'Common' as RarityName,
            winType: 'claim',
          };
        } else if (winType && serverRarity) {
          const normalizedRarity = normalizeRarityName(serverRarity);
          if (!normalizedRarity) {
            console.warn('Server sent unsupported rarity for slots victory:', serverRarity);
          } else {
            pendingWinRef.current = {
              symbol: winningSymbolFromArray,
              rarity: normalizedRarity,
              winType: winType as 'card' | 'aspect',
              setId,
              setName,
              spinResultId,
            };
          }
        }
      }
      return true;
    } catch (error) {
      console.error('Failed to spin slots:', error);
      const errorMessage = error instanceof Error ? error.message : 'Failed to process spin';
      if (!isAutospinningRef.current) {
        TelegramUtils.showAlert(errorMessage);
      }
      setStripDurations(Array(SLOT_REEL_COUNT).fill(0));
      setStripTransforms(Array(SLOT_REEL_COUNT).fill(0));
      setReelStates([...INITIAL_REEL_STATES]);
      setSpinning(false);
      return false;
    }
  }, [
    spinning,
    symbols,
    userSpins,
    userId,
    chatId,
    initData,
    onSpinsUpdate,
    onMegaspinUpdate,
    clearReelTimeouts,
    setReelStates,
    setResults,
    addReelTimeout,
    finalizeSpin,
    setSpinning,
    resetRarityWheel,
    getSpeedMultiplier,
    selectedMultiplier,
    resolveWinningSymbols,
  ]);

  const handleSpinButtonMouseDown = useCallback(() => {
    if (spinning || symbols.length === 0 || userSpins.loading || userSpins.count < selectedMultiplier || isAutospinning) {
      return;
    }

    // Don't reset the flag here - it should persist until after onClick fires
    longPressTimerRef.current = setTimeout(() => {
      longPressTriggeredRef.current = true;
      const newMode = !isAutospinMode;
      setIsAutospinMode(newMode);
      TelegramUtils.triggerHapticImpact(newMode ? 'medium' : 'light');
    }, 1000);
  }, [spinning, symbols.length, userSpins.loading, userSpins.count, isAutospinMode, isAutospinning, selectedMultiplier]);

  const handleSpinButtonMouseUp = useCallback(() => {
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
    
    // Reset the flag after a short delay to ensure onClick sees it
    if (longPressTriggeredRef.current) {
      setTimeout(() => {
        longPressTriggeredRef.current = false;
      }, 100);
    }
  }, []);

  const handleSpinButtonMouseLeave = useCallback(() => {
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  }, []);

  const handleSpinButtonTouchCancel = useCallback(() => {
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  }, []);

  // Wait for a spin to complete (watching spinning state)
  const waitForSpinComplete = useCallback((): Promise<void> => {
    return new Promise((resolve) => {
      // Check spinning state periodically until it becomes false
      const checkInterval = setInterval(() => {
        // If spinning is false and reels are idle, spin is complete
        if (!useSlotsStore.getState().spinning) {
          clearInterval(checkInterval);
          // Add a small delay to ensure finalizeSpin has completed
          setTimeout(resolve, 100);
        }
      }, 100);
    });
  }, []);

  // Start autospin loop
  const handleStartAutospin = useCallback(async () => {
    if (spinning || symbols.length === 0 || userSpins.loading || userSpins.count < selectedMultiplier) {
      return;
    }

    // Set autospin state
    autospinStopRef.current = false;
    isAutospinningRef.current = true;
    setIsAutospinning(true);
    
    // Reset autospin win counters
    autospinCardsWonRef.current = 0;
    autospinAspectsWonRef.current = 0;
    autospinClaimPointsWonRef.current = 0;
    
    TelegramUtils.triggerHapticImpact('heavy');

    // Autospin loop
    const runAutospinLoop = async () => {
      while (!autospinStopRef.current) {
        // Check if we have enough spins for the selected bet multiplier
        const currentSpinCount = userSpins.count;
        if (currentSpinCount < selectedMultiplier) {
          break;
        }

        // Trigger a spin
        const success = await handleSpin();
        
        if (!success) {
          // If spin failed, stop autospin
          break;
        }

        // Wait for the spin to complete
        await waitForSpinComplete();
        
        // Small delay between spins
        await new Promise<void>((resolve) => setTimeout(resolve, 200));
      }

      // Autospin ended - show summary if anything was won
      const cardsWon = autospinCardsWonRef.current;
      const aspectsWon = autospinAspectsWonRef.current;
      const claimPointsWon = autospinClaimPointsWonRef.current;
      
      if (cardsWon > 0 || aspectsWon > 0 || claimPointsWon > 0) {
        const lines: string[] = ['Autospin results:', ''];
        if (cardsWon > 0) {
          lines.push(`Cards won: ${cardsWon}`);
        }
        if (aspectsWon > 0) {
          lines.push(`Aspects won: ${aspectsWon}`);
        }
        if (claimPointsWon > 0) {
          lines.push(`Claim points: ${claimPointsWon}`);
        }
        TelegramUtils.showAlert(lines.join('\n'));
        TelegramUtils.triggerHapticNotification('success');
      }
      
      isAutospinningRef.current = false;
      setIsAutospinning(false);
      setIsAutospinStopping(false);
      TelegramUtils.triggerHapticImpact('light');
    };

    runAutospinLoop();
  }, [spinning, symbols.length, userSpins.loading, userSpins.count, handleSpin, waitForSpinComplete]);

  // Stop autospin
  const handleStopAutospin = useCallback(() => {
    autospinStopRef.current = true;
    setIsAutospinStopping(true);
    TelegramUtils.triggerHapticImpact('medium');
  }, []);



  const handleMegaspin = useCallback(async () => {
    if (spinning || symbols.length === 0 || megaspinData.loading) {
      return;
    }

    if (!megaspinData.megaspinAvailable) {
      TelegramUtils.showAlert('No megaspin available! Keep spinning to earn one.');
      return;
    }

    TelegramUtils.triggerHapticImpact('heavy');

    resetRarityWheel();
    setSpinning(true);
    setIsMegaspinning(true);
    setReelStates(Array.from({ length: SLOT_REEL_COUNT }, () => 'spinning' as ReelState));
    clearReelTimeouts();
    pendingWinRef.current = null;

    try {
      // Atomic megaspin: consume + roll + persist token in one call.
      const spinResult = await ApiService.megaspin(userId, chatId, initData);

      if (!spinResult.success) {
        const message = spinResult.message || 'Failed to use megaspin';
        TelegramUtils.showAlert(message);
        setSpinning(false);
        setIsMegaspinning(false);
        setReelStates([...INITIAL_REEL_STATES]);
        if (spinResult.megaspin) {
          onMegaspinUpdate(spinResult.megaspin);
        }
        return;
      }

      if (spinResult.megaspin) {
        onMegaspinUpdate(spinResult.megaspin);
      }

      const slotResults = spinResult.slot_results;
      const serverRarity = spinResult.rarity ?? null;
      const winType = spinResult.win_type ?? null;
      const setId = spinResult.set_id ?? null;
      const setName = spinResult.set_name ?? null;
      const spinResultId = spinResult.spin_result_id ?? null;

      const { symbols: effectiveSymbols, indices: rawIndices } = resolveWinningSymbols(
        slotResults,
        spinResult.winning_symbol,
      );
      const normalizedResults = [...rawIndices];

      while (normalizedResults.length < SLOT_REEL_COUNT) {
        normalizedResults.push(0);
      }

      setResults(normalizedResults.slice(0, SLOT_REEL_COUNT));

      const spinTransforms = normalizedResults.map((result) =>
        computeSlotSpinTransforms(result, effectiveSymbols.length)
      );
      const finalTransforms = spinTransforms.map((value) => value.final);
      const initialTransforms = spinTransforms.map((value) => value.initial);
      const megaspinSpeedMultiplier = getSpeedMultiplier();
      const durations = normalizedResults.map(
        (_, index) => (SLOT_BASE_SPIN_DURATION_MS + index * SLOT_SPIN_DURATION_STAGGER_MS) / megaspinSpeedMultiplier
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

      // Megaspin is guaranteed win - set up pending win
      if (serverRarity && slotResults.length > 0) {
        const winningIndex = normalizedResults[0];
        const winningSymbolFromArray = effectiveSymbols[winningIndex];

        if (winningSymbolFromArray) {
          const normalizedRarity = normalizeRarityName(serverRarity);
          if (normalizedRarity) {
            pendingWinRef.current = {
              symbol: winningSymbolFromArray,
              rarity: normalizedRarity,
              winType: winType as 'card' | 'aspect',
              setId,
              setName,
              spinResultId,
            };
          }
        }
      }
    } catch (error) {
      console.error('Failed to use megaspin:', error);
      const errorMessage = error instanceof Error ? error.message : 'Failed to use megaspin';
      TelegramUtils.showAlert(errorMessage);
      setStripDurations(Array(SLOT_REEL_COUNT).fill(0));
      setStripTransforms(Array(SLOT_REEL_COUNT).fill(0));
      setReelStates([...INITIAL_REEL_STATES]);
      setSpinning(false);
      setIsMegaspinning(false);
    }
  }, [
    spinning,
    symbols,
    megaspinData,
    userId,
    chatId,
    initData,
    onMegaspinUpdate,
    clearReelTimeouts,
    setReelStates,
    resolveWinningSymbols,
    setResults,
    addReelTimeout,
    finalizeSpin,
    setSpinning,
    resetRarityWheel,
    getSpeedMultiplier
  ]);

  useEffect(() => {
    return () => {
      if (longPressTimerRef.current) {
        clearTimeout(longPressTimerRef.current);
      }
    };
  }, []);

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
    return <Title title="🎰 Slots" leftContent={claimPoints != null ? <ClaimPointsBadge count={claimPoints} /> : undefined} rightContent={<SpinsBadge count={userSpins.count} />} fullscreen />;
  }

  return (
    <div className="slots-container">
      <Title title="🎰 Slots" leftContent={claimPoints != null ? <ClaimPointsBadge count={claimPoints} /> : undefined} rightContent={<SpinsBadge count={userSpins.count} />} />

      <div className={`slot-machine-container ${isMegaspinning ? 'slot-machine-megaspin' : ''}`}>
        <div className={`slot-reels ${isWinning ? 'slot-reels-winning' : ''} ${isMegaspinning ? 'slot-reels-megaspin' : ''}`}>
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
                className={`spin-button ${isAutospinMode ? 'spin-button-autospin' : ''} ${isAutospinning ? 'spin-button-stop' : ''}`}
                onClick={isAutospinning ? handleStopAutospin : (isAutospinMode ? handleStartAutospin : handleSpin)}
                onMouseDown={handleSpinButtonMouseDown}
                onMouseUp={handleSpinButtonMouseUp}
                onMouseLeave={handleSpinButtonMouseLeave}
                onTouchStart={handleSpinButtonMouseDown}
                onTouchEnd={handleSpinButtonMouseUp}
                onTouchCancel={handleSpinButtonTouchCancel}
                disabled={(isAutospinning && isAutospinStopping) || (!isAutospinning && (spinning || symbols.length === 0 || userSpins.loading || userSpins.count < selectedMultiplier))}
              >
                {isAutospinning
                  ? 'STOP'
                  : spinning
                    ? 'SPINNING…'
                    : isAutospinMode
                      ? 'AUTOSPIN'
                      : 'SPIN'}
              </button>

              {/* Megaspin Button */}
              <button
                className={`megaspin-button ${megaspinData.megaspinAvailable ? 'megaspin-button-ready' : ''} ${isMegaspinning ? 'megaspin-button-spinning' : ''}`}
                onClick={handleMegaspin}
                disabled={spinning || symbols.length === 0 || megaspinData.loading || !megaspinData.megaspinAvailable || isAutospinning}
              >
                <div 
                  className="megaspin-fill"
                  style={{
                    width: megaspinData.megaspinAvailable 
                      ? '100%' 
                      : `${((megaspinData.totalSpinsRequired - megaspinData.spinsUntilMegaspin) / megaspinData.totalSpinsRequired) * 100}%`
                  }}
                />
                <span className="megaspin-text">
                  MEGA SPIN
                </span>
              </button>

              <div className="slot-bet-buttons">
                {SLOT_BET_MULTIPLIERS.map((amount) => {
                  const insufficient = userSpins.count < amount;
                  const isSelected = selectedMultiplier === amount;
                  const isBetLocked = spinning || isAutospinning || userSpins.loading;
                  return (
                    <button
                      key={amount}
                      type="button"
                      className={`slot-bet-option ${isSelected ? 'selected' : ''}`}
                      onClick={() => {
                        if (isBetLocked || insufficient) return;
                        setSelectedMultiplier(amount);
                        TelegramUtils.triggerHapticSelection();
                      }}
                      disabled={isBetLocked || insufficient}
                    >
                      {amount}
                      <span className="casino-coin-inline slot-bet-coin" />
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Slots;