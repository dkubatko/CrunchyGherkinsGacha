import { create } from 'zustand';

export interface PokerPlayer {
  user_id: number;
  seat_position: number;
  betting_balance: number;
  current_bet: number;
  total_bet: number;
  status: string;
  last_action?: string;
  slot_iconb64?: string;
}

export interface PokerGameState {
  game_id?: number;
  chat_id: string;
  status: string;
  pot: number;
  current_bet: number;
  min_betting_balance?: number;
  community_cards: Array<{ suit: string; rank: string }>;
  countdown_start_time?: string;
  current_player_turn?: number;
  dealer_position?: number;
  players: PokerPlayer[];
}

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

interface PokerState {
  // Connection state
  connectionStatus: ConnectionStatus;
  error: string | null;
  
  // Game state
  gameState: PokerGameState | null;
  
  // Player slot icons (cached separately to avoid sending on every update)
  playerSlotIcons: Record<number, string>; // user_id -> slot_iconb64
  
  // Actions
  setConnectionStatus: (status: ConnectionStatus) => void;
  setError: (error: string | null) => void;
  setGameState: (gameState: PokerGameState | null) => void;
  updateGameState: (updates: Partial<PokerGameState>) => void;
  updatePlayerSlotIcons: (icons: Record<number, string>) => void;
  reset: () => void;
}

const initialState = {
  connectionStatus: 'disconnected' as ConnectionStatus,
  error: null,
  gameState: null,
  playerSlotIcons: {},
};

export const usePokerStore = create<PokerState>((set) => ({
  ...initialState,

  setConnectionStatus: (status) => set({ connectionStatus: status }),
  
  setError: (error) => set({ error }),
  
  setGameState: (gameState) => {
    // Extract and cache slot icons from players if present
    if (gameState?.players) {
      const icons: Record<number, string> = {};
      let hasIcons = false;
      
      gameState.players.forEach((player) => {
        if (player.slot_iconb64) {
          icons[player.user_id] = player.slot_iconb64;
          hasIcons = true;
        }
      });
      
      if (hasIcons) {
        set((state) => ({
          gameState,
          playerSlotIcons: { ...state.playerSlotIcons, ...icons }
        }));
        return;
      }
    }
    
    set({ gameState });
  },
  
  updateGameState: (updates) => set((state) => ({
    gameState: state.gameState ? { ...state.gameState, ...updates } : null
  })),
  
  updatePlayerSlotIcons: (icons) => set((state) => ({
    playerSlotIcons: { ...state.playerSlotIcons, ...icons }
  })),
  
  reset: () => set(initialState),
}));
