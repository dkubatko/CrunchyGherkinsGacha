export const SLOT_REEL_COUNT = 3;
export const SLOT_VISIBLE_ROWS = 3;
export const SLOT_STRIP_REPEAT_MULTIPLIER = 12;
export const SLOT_SYMBOL_HEIGHT = 88;
export const SLOT_BASE_SPIN_DURATION_MS = 1100;
export const SLOT_SPIN_DURATION_STAGGER_MS = 250;
export const SLOT_STOPPING_LEAD_MS = 200;
export const SLOT_MIN_SYMBOLS_PER_SECOND = 18;

export const computeSlotSpinTransforms = (
  symbolIndex: number,
  symbolCount: number
): { initial: number; final: number } => {
  if (symbolCount <= 0) {
    return { initial: 0, final: 0 };
  }

  const safeIndex = ((symbolIndex % symbolCount) + symbolCount) % symbolCount;
  const totalSymbols = symbolCount * SLOT_STRIP_REPEAT_MULTIPLIER;
  const middleOffsetLoops = Math.max(2, Math.floor(SLOT_STRIP_REPEAT_MULTIPLIER / 2));
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
