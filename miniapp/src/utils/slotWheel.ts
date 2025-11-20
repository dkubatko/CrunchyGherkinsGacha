export const SLOT_REEL_COUNT = 3;
export const SLOT_VISIBLE_ROWS = 3;
export const SLOT_STRIP_REPEAT_MULTIPLIER = 5;
export const SLOT_MIN_STRIP_SYMBOLS = 50;
export const SLOT_SYMBOL_HEIGHT = 90;
export const SLOT_BASE_SPIN_DURATION_MS = 1600;
export const SLOT_SPIN_DURATION_STAGGER_MS = 380;
export const SLOT_MIN_SYMBOLS_PER_SECOND = 48;
export const SLOT_SPIN_TIMING_FUNCTION = 'cubic-bezier(0.2, 0.86, 0.5, 1.02)';

const resolveStripRepeatMultiplier = (symbolCount: number): number => {
  if (symbolCount <= 0) {
    return SLOT_STRIP_REPEAT_MULTIPLIER;
  }

  const minMultiplier = Math.ceil(SLOT_MIN_STRIP_SYMBOLS / symbolCount);
  return Math.max(SLOT_STRIP_REPEAT_MULTIPLIER, minMultiplier);
};

export const computeTotalSlotSymbols = (symbolCount: number): number => {
  if (symbolCount <= 0) {
    return 0;
  }

  return symbolCount * resolveStripRepeatMultiplier(symbolCount);
};

export const computeSlotSpinTransforms = (
  symbolIndex: number,
  symbolCount: number
): { initial: number; final: number } => {
  if (symbolCount <= 0) {
    return { initial: 0, final: 0 };
  }

  const safeIndex = ((symbolIndex % symbolCount) + symbolCount) % symbolCount;
  const totalSymbols = computeTotalSlotSymbols(symbolCount);
  if (totalSymbols <= 0) {
    return { initial: 0, final: 0 };
  }

  const stripRepeatMultiplier = totalSymbols / symbolCount;
  const middleOffsetLoops = Math.max(2, Math.floor(stripRepeatMultiplier / 2));
  const targetPosition = safeIndex + symbolCount * middleOffsetLoops;
  const clampedPosition = Math.min(totalSymbols - 2, Math.max(1, targetPosition));
  const topIndex = clampedPosition - 1;
  const finalTransform = -(topIndex * SLOT_SYMBOL_HEIGHT);

  const availableForwardLoops = Math.max(
    1,
    Math.floor((totalSymbols - SLOT_VISIBLE_ROWS - topIndex) / symbolCount)
  );
  const minLoopsForDuration = Math.max(
    2,
    Math.ceil(
      (SLOT_BASE_SPIN_DURATION_MS / 1000) *
        (SLOT_MIN_SYMBOLS_PER_SECOND / symbolCount)
    )
  );
  const loopsForward = Math.max(2, Math.min(availableForwardLoops, minLoopsForDuration));
  const startIndex = Math.min(
    totalSymbols - SLOT_VISIBLE_ROWS,
    topIndex + loopsForward * symbolCount
  );
  const initialTransform = -(startIndex * SLOT_SYMBOL_HEIGHT);

  return { initial: initialTransform, final: finalTransform };
};

export const computeSlotStaticTransform = (symbolIndex: number, symbolCount: number): number => {
  if (symbolCount <= 0) {
    return 0;
  }

  const safeIndex = ((symbolIndex % symbolCount) + symbolCount) % symbolCount;
  const topIndex = (safeIndex - 1 + symbolCount) % symbolCount;

  return -(topIndex * SLOT_SYMBOL_HEIGHT);
};
