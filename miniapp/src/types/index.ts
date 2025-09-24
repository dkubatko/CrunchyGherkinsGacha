export interface CardData {
  id: number;
  base_name: string;
  modifier: string;
  rarity: string;
  owner?: string;
  chat_id?: string | null;
}

export interface OrientationData {
  alpha: number;
  beta: number;
  gamma: number;
  isStarted: boolean;
}

export type View = 'current' | 'all';

export interface UserData {
  username: string;
  isOwnCollection: boolean;
  enableTrade: boolean;
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