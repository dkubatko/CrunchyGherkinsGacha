export interface CardData {
  id: number;
  base_name: string;
  modifier: string;
  rarity: string;
  owner?: string;
  user_id?: number | null;
  chat_id?: string | null;
  locked?: boolean;
  set_name?: string | null;
}

export interface OrientationData {
  alpha: number;
  beta: number;
  gamma: number;
  isStarted: boolean;
}

export type View = 'current' | 'all' | 'slots' | 'profile';

export interface UserSummary {
  user_id: number;
  username?: string | null;
  display_name?: string | null;
}

export interface UserCollectionResponse {
  user: UserSummary;
  cards: CardData[];
}

export interface CardConfigResponse {
  burn_rewards: Record<string, number>;
  lock_costs: Record<string, number>;
}

export interface SlotSymbolSummary {
  id: number;
  display_name?: string | null;
  slot_iconb64?: string | null;
  type: 'user' | 'character' | 'claim';
}

export interface SlotSymbolInfo {
  id: number;
  type: string;
}

export interface UserData {
  currentUserId: number;
  targetUserId: number;
  isOwnCollection: boolean;
  enableTrade: boolean;
  chatId?: string | null;
  collectionDisplayName?: string | null;
  collectionUsername?: string | null;
  // Single card view mode: if singleCardId is set, the app should render only that card
  singleCardId?: number | null;
  singleCardView?: boolean; // Convenience boolean to avoid recomputing
  // Casino view mode: if casinoView is true, the app should render the casino catalog
  casinoView?: boolean;
}

export interface AppState {
  cards: CardData[];
  allCards: CardData[];
  currentIndex: number;
  loading: boolean;
  error: string | null;
  allCardsLoading: boolean;
  allCardsError: string | null;
  view: View;
  showModal: boolean;
  modalCard: CardData | null;
}

export interface SlotVerifyResponse {
  is_win: boolean;
  slot_results: SlotSymbolInfo[];
  rarity?: string | null;
}

export interface MegaspinInfo {
  spins_until_megaspin: number;
  total_spins_required: number;
  megaspin_available: boolean;
}

export interface ClaimBalanceState {
  balance: number | null;
  loading: boolean;
  error?: string;
}

export interface UserAchievement {
  id: number;
  name: string;
  description: string;
  icon_b64?: string | null;
  unlocked_at: string;
}

export interface UserProfile {
  user_id: number;
  username: string;
  display_name?: string | null;
  profile_imageb64?: string | null;
  claim_balance: number;
  spin_balance: number;
  card_count: number;
  achievements: UserAchievement[];
}

export interface ProfileState {
  profile: UserProfile | null;
  loading: boolean;
  error?: string;
}

// Ride the Bus types
export interface RTBCardInfo {
  card_id: number;
  rarity: string;
  title: string;
  image_b64: string | null;
}

export interface RTBGameResponse {
  game_id: number;
  status: 'active' | 'won' | 'lost' | 'cashed_out';
  bet_amount: number;
  current_position: number;
  current_multiplier: number;
  next_multiplier: number;
  potential_payout: number;
  cards: RTBCardInfo[];
  started_timestamp: string;
  last_updated_timestamp: string;
  spins_balance: number | null;
  cooldown_ends_at: string | null;  // ISO timestamp when cooldown ends (for won/cashed_out)
}

export interface RTBGuessResponse {
  correct: boolean;
  game: RTBGameResponse;
  actual_comparison: 'higher' | 'lower';
  message: string;
}

export interface RTBCashOutResponse {
  success: boolean;
  payout: number;
  new_spin_total: number;
  message: string;
  game: RTBGameResponse;
}

export interface RTBConfigResponse {
  min_bet: number;
  max_bet: number;
  cards_per_game: number;
  multiplier_progression: Record<number, number>;
  rarity_order: string[];
  available: boolean;
  unavailable_reason: string | null;
}
