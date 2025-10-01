import { RARITY_SEQUENCE, type RarityName } from './rarityStyles';

export const RARITY_WHEEL_VISIBLE_ROWS = 3;
export const RARITY_WHEEL_SYMBOL_HEIGHT = 48;
export const RARITY_WHEEL_STRIP_REPEAT_MULTIPLIER = 8;
export const RARITY_WHEEL_MIN_SYMBOLS_PER_SECOND = 10;
export const RARITY_WHEEL_BASE_DURATION_MS = 2000; // slightly quicker easing tail
export const RARITY_WHEEL_FINAL_SETTLE_DELAY_MS = 420;

export const generateRarityWheelStrip = (): RarityName[] => {
  const repeated: RarityName[] = [];
  const total = RARITY_SEQUENCE.length * RARITY_WHEEL_STRIP_REPEAT_MULTIPLIER;

  for (let i = 0; i < total; i += 1) {
    repeated.push(RARITY_SEQUENCE[i % RARITY_SEQUENCE.length]);
  }

  return repeated;
};

export const computeRarityWheelTransforms = (
  symbolIndex: number,
  symbolCount: number
): { initial: number; final: number } => {
  if (symbolCount <= 0) {
    return { initial: 0, final: 0 };
  }

  const safeIndex = ((symbolIndex % symbolCount) + symbolCount) % symbolCount;
  const totalSymbols = symbolCount * RARITY_WHEEL_STRIP_REPEAT_MULTIPLIER;
  const middleOffsetLoops = Math.max(2, Math.floor(RARITY_WHEEL_STRIP_REPEAT_MULTIPLIER / 2));
  const targetPosition = safeIndex + symbolCount * middleOffsetLoops;
  const clampedPosition = Math.min(totalSymbols - 2, Math.max(1, targetPosition));
  const topIndex = clampedPosition - 1;
  const finalTransform = -(topIndex * RARITY_WHEEL_SYMBOL_HEIGHT);

  const availableForwardLoops = Math.max(
    1,
    Math.floor((totalSymbols - RARITY_WHEEL_VISIBLE_ROWS - topIndex) / symbolCount)
  );
  const minLoopsForDuration = Math.max(
    2,
    Math.ceil(
      (RARITY_WHEEL_BASE_DURATION_MS / 1000) *
        (RARITY_WHEEL_MIN_SYMBOLS_PER_SECOND / symbolCount)
    )
  );
  const loopsForward = Math.max(2, Math.min(availableForwardLoops, minLoopsForDuration));
  const startIndex = Math.min(
    totalSymbols - RARITY_WHEEL_VISIBLE_ROWS,
    topIndex + loopsForward * symbolCount
  );
  const initialTransform = -(startIndex * RARITY_WHEEL_SYMBOL_HEIGHT);

  return { initial: initialTransform, final: finalTransform };
};

export const computeRarityWheelStaticTransform = (symbolIndex: number, symbolCount: number): number => {
  if (symbolCount <= 0) {
    return 0;
  }

  const safeIndex = ((symbolIndex % symbolCount) + symbolCount) % symbolCount;
  const topIndex = (safeIndex - 1 + symbolCount) % symbolCount;

  return -(topIndex * RARITY_WHEEL_SYMBOL_HEIGHT);
};
