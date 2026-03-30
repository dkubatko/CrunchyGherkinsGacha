export interface AdminSet {
  id: number;
  season_id: number;
  name: string;
  source: string;
  description: string;
  active: boolean;
  aspect_count: number;
  slot_icon_b64?: string | null;
}

export interface AdminAspectDef {
  id: number;
  name: string;
  rarity: string;
  set_id: number;
  season_id: number;
  created_at: string;
  owned_count: number;
}

export interface AdminAspectDefCreate {
  set_id: number;
  season_id: number;
  name: string;
  rarity: string;
}

export interface AdminAspectDefUpdate {
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
