import { create } from 'zustand';
import { RARITY_SEQUENCE, type RarityName } from '../utils/rarityStyles';
import { computeRarityWheelStaticTransform } from '../utils/rarityWheel';

interface SlotSymbol {
  id: number;
  iconb64?: string;
  displayName?: string;
  type: 'user' | 'character' | 'claim';
}

type ReelState = 'idle' | 'spinning' | 'stopped';

interface SlotsState {
  symbols: SlotSymbol[];
  results: number[];
  spinning: boolean;
  reelStates: ReelState[];
  reelTimeouts: NodeJS.Timeout[];
  rarityWheelActive: boolean;
  rarityWheelTarget: RarityName | null;
  rarityWheelSpinning: boolean;
  rarityWheelTransform: number;
  rarityWheelDuration: number;
  rarityWheelTimeout: ReturnType<typeof setTimeout> | null;
  setSymbols: (symbols: SlotSymbol[]) => void;
  setResults: (results: number[]) => void;
  setSpinning: (spinning: boolean) => void;
  setReelStates: (states: ReelState[] | ((prev: ReelState[]) => ReelState[])) => void;
  addReelTimeout: (timeout: NodeJS.Timeout) => void;
  clearReelTimeouts: () => void;
  setRarityWheelState: (partial: Partial<RarityWheelState>) => void;
  setRarityWheelTimeout: (timeout: ReturnType<typeof setTimeout> | null) => void;
  clearRarityWheelTimeout: () => void;
  resetRarityWheel: () => void;
  reset: () => void;
}

type RarityWheelState = Pick<
  SlotsState,
  | 'rarityWheelActive'
  | 'rarityWheelTarget'
  | 'rarityWheelSpinning'
  | 'rarityWheelTransform'
  | 'rarityWheelDuration'
>;

const INITIAL_RESULTS: number[] = [0, 1, 2];
const INITIAL_REEL_STATES: ReelState[] = ['idle', 'idle', 'idle'];

export const useSlotsStore = create<SlotsState>((set, get) => ({
  symbols: [],
  results: [...INITIAL_RESULTS],
  spinning: false,
  reelStates: [...INITIAL_REEL_STATES],
  reelTimeouts: [],
  rarityWheelActive: false,
  rarityWheelTarget: null,
  rarityWheelSpinning: false,
  rarityWheelTransform: computeRarityWheelStaticTransform(0, RARITY_SEQUENCE.length),
  rarityWheelDuration: 0,
  rarityWheelTimeout: null,

  setSymbols: (symbols) => set({ symbols }),
  setResults: (results) => set({ results }),
  setSpinning: (spinning) => set({ spinning }),
  setReelStates: (states) => set((state) => ({
    reelStates: typeof states === 'function' ? states(state.reelStates) : states
  })),
  addReelTimeout: (timeout) => set((state) => ({
    reelTimeouts: [...state.reelTimeouts, timeout]
  })),
  clearReelTimeouts: () => {
    const { reelTimeouts } = get();
    reelTimeouts.forEach((timeout) => clearTimeout(timeout));
    set({ reelTimeouts: [] });
  },
  setRarityWheelState: (partial) => set(partial),
  setRarityWheelTimeout: (timeout) => {
    const { rarityWheelTimeout } = get();
    if (rarityWheelTimeout && rarityWheelTimeout !== timeout) {
      clearTimeout(rarityWheelTimeout);
    }
    set({ rarityWheelTimeout: timeout });
  },
  clearRarityWheelTimeout: () => {
    const { rarityWheelTimeout } = get();
    if (rarityWheelTimeout) {
      clearTimeout(rarityWheelTimeout);
    }
    set({ rarityWheelTimeout: null });
  },
  resetRarityWheel: () => {
    const { clearRarityWheelTimeout } = get();
    clearRarityWheelTimeout();
    set({
      rarityWheelActive: false,
      rarityWheelTarget: null,
      rarityWheelSpinning: false,
      rarityWheelTransform: computeRarityWheelStaticTransform(0, RARITY_SEQUENCE.length),
      rarityWheelDuration: 0,
    });
  },
  reset: () => {
    const { reelTimeouts, resetRarityWheel } = get();
    reelTimeouts.forEach((timeout) => clearTimeout(timeout));
    resetRarityWheel();
    set({
      results: [...INITIAL_RESULTS],
      spinning: false,
      reelStates: [...INITIAL_REEL_STATES],
      reelTimeouts: []
    });
  }
}));
