import { create } from 'zustand';

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

interface SlotsState {
  spinState: SpinState;
  raritySpinState: RaritySpinState;
  symbols: SlotSymbol[];
  reelTimeouts: NodeJS.Timeout[];
  rarityTimeouts: NodeJS.Timeout[];
  
  // Actions
  setSpinState: (spinState: SpinState | ((prev: SpinState) => SpinState)) => void;
  setRaritySpinState: (raritySpinState: RaritySpinState | ((prev: RaritySpinState) => RaritySpinState)) => void;
  setSymbols: (symbols: SlotSymbol[]) => void;
  addReelTimeout: (timeout: NodeJS.Timeout) => void;
  addRarityTimeout: (timeout: NodeJS.Timeout) => void;
  clearReelTimeouts: () => void;
  clearRarityTimeouts: () => void;
  clearAllTimeouts: () => void;
  reset: () => void;
}

const initialSpinState: SpinState = {
  spinning: false,
  reelStates: ['idle', 'idle', 'idle'],
  results: [0, 1, 2]
};

const initialRaritySpinState: RaritySpinState = {
  visible: false,
  spinning: false,
  result: 0
};

export const useSlotsStore = create<SlotsState>((set, get) => ({
  spinState: initialSpinState,
  raritySpinState: initialRaritySpinState,
  symbols: [],
  reelTimeouts: [],
  rarityTimeouts: [],
  
  setSpinState: (spinState) => set((state) => ({
    spinState: typeof spinState === 'function' ? spinState(state.spinState) : spinState
  })),
  
  setRaritySpinState: (raritySpinState) => set((state) => ({
    raritySpinState: typeof raritySpinState === 'function' ? raritySpinState(state.raritySpinState) : raritySpinState
  })),
  
  setSymbols: (symbols) => set({ symbols }),
  
  addReelTimeout: (timeout) => set((state) => ({
    reelTimeouts: [...state.reelTimeouts, timeout]
  })),
  
  addRarityTimeout: (timeout) => set((state) => ({
    rarityTimeouts: [...state.rarityTimeouts, timeout]
  })),
  
  clearReelTimeouts: () => {
    const { reelTimeouts } = get();
    reelTimeouts.forEach(timeout => clearTimeout(timeout));
    set({ reelTimeouts: [] });
  },
  
  clearRarityTimeouts: () => {
    const { rarityTimeouts } = get();
    rarityTimeouts.forEach(timeout => clearTimeout(timeout));
    set({ rarityTimeouts: [] });
  },
  
  clearAllTimeouts: () => {
    const state = get();
    state.reelTimeouts.forEach(timeout => clearTimeout(timeout));
    state.rarityTimeouts.forEach(timeout => clearTimeout(timeout));
    set({ reelTimeouts: [], rarityTimeouts: [] });
  },
  
  reset: () => set({
    spinState: initialSpinState,
    raritySpinState: initialRaritySpinState,
    reelTimeouts: [],
    rarityTimeouts: []
  })
}));
