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
  type_id?: number | null;
  created_at: string;
  owned_count: number;
}

export interface AdminAspectDefCreate {
  set_id: number;
  season_id: number;
  name: string;
  rarity: string;
  type_id?: number | null;
}

export interface AdminAspectDefUpdate {
  name?: string;
  rarity?: string;
  set_id?: number;
  type_id?: number | null;
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

export interface AdminAspectType {
  id: number;
  name: string;
  description?: string | null;
  created_at?: string | null;
  usage_count: number;
}

export interface AdminAspectTypeCreate {
  name: string;
  description?: string | null;
}

export interface AdminAspectTypeUpdate {
  name?: string;
  description?: string;
}

export interface AdminAspectByType {
  id: number;
  name: string;
  rarity: string;
  set_id: number;
  set_name?: string | null;
  season_id: number;
}
