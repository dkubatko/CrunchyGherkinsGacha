export interface AdminSet {
  id: number;
  season_id: number;
  name: string;
  source: string;
  description: string;
  active: boolean;
  modifier_count: number;
}

export interface AdminModifier {
  id: number;
  name: string;
  rarity: string;
  set_id: number;
  season_id: number;
  created_at: string;
  card_count: number;
}

export interface AdminModifierCreate {
  set_id: number;
  season_id: number;
  name: string;
  rarity: string;
}

export interface AdminModifierUpdate {
  name?: string;
  rarity?: string;
  set_id?: number;
}

export interface AdminSetCreate {
  name: string;
  source?: string;
  description?: string;
  active?: boolean;
}

export interface AdminSetUpdate {
  name?: string;
  source?: string;
  description?: string;
  active?: boolean;
}

export interface AdminMe {
  admin_id: number;
  username: string;
}
