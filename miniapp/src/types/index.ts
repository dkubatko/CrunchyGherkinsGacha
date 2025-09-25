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

export type View = 'current' | 'all';

export interface UserSummary {
  user_id: number;
  username?: string | null;
  display_name?: string | null;
}

export interface UserCollectionResponse {
  user: UserSummary;
  cards: CardData[];
}

export interface UserData {
  currentUserId: number;
  targetUserId: number;
  isOwnCollection: boolean;
  enableTrade: boolean;
  chatId?: string | null;
  collectionDisplayName?: string | null;
  collectionUsername?: string | null;
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