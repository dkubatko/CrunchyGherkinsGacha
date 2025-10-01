export interface CardData {
  id: number;
  base_name: string;
  modifier: string;
  rarity: string;
  owner?: string;
  user_id?: number | null;
  chat_id?: string | null;
}

export interface OrientationData {
  alpha: number;
  beta: number;
  gamma: number;
  isStarted: boolean;
}

export type View = 'current' | 'all' | 'slots';

export interface UserSummary {
  user_id: number;
  username?: string | null;
  display_name?: string | null;
}

export interface UserCollectionResponse {
  user: UserSummary;
  cards: CardData[];
}

export interface ChatUserCharacterSummary {
  id: number;
  display_name?: string | null;
  slot_iconb64?: string | null;
  type: 'user' | 'character';
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
  // Slots view mode: if slotsView is true, the app should render the slots mini-game
  slotsView?: boolean;
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
  results: number[]; // Array of 3 reel results (indices)
  rarity?: string | null;
}