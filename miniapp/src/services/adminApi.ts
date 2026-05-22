import type {
  AdminSet,
  AdminAspectDef,
  AdminAspectDefCreate,
  AdminAspectDefUpdate,
  AdminAspectType,
  AdminAspectTypeCreate,
  AdminAspectTypeUpdate,
  AdminAspectByType,
  AdminSetCreate,
  AdminSetUpdate,
  AdminMe,
} from '../types/admin';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

interface BulkAspectDefItem {
  set_id: number;
  season_id: number;
  name: string;
  rarity: string;
}

/** Event name fired when the API rejects a request with 401. */
export const ADMIN_SESSION_EXPIRED_EVENT = 'admin:session-expired';

export class AdminApiService {
  private static async handleResponse<T>(response: Response): Promise<T> {
    if (response.status === 401) {
      // Notify the app shell so it can route to login without a full reload.
      window.dispatchEvent(new CustomEvent(ADMIN_SESSION_EXPIRED_EVENT));
      throw new Error('Session expired. Please log in again.');
    }
    if (!response.ok) {
      let detail = `Request failed (${response.status})`;
      try {
        const body = await response.json();
        if (body?.detail) detail = body.detail;
      } catch {
        /* ignore parse errors */
      }
      throw new Error(detail);
    }
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    if (!text) return undefined as T;
    return JSON.parse(text) as T;
  }

  private static request<T>(path: string, init?: RequestInit): Promise<T> {
    return fetch(`${API_BASE_URL}${path}`, {
      credentials: 'include',
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers || {}),
      },
    }).then((r) => this.handleResponse<T>(r));
  }

  // ── Auth ──────────────────────────────────────────────────────────────

  static login(username: string, password: string): Promise<{ status: string }> {
    return this.request('/admin/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  }

  static verifyOtp(
    username: string,
    code: string,
    remember = false,
  ): Promise<{ ok: boolean; expires_at: string }> {
    return this.request('/admin/auth/verify-otp', {
      method: 'POST',
      body: JSON.stringify({ username, code, remember }),
    });
  }

  static logout(): Promise<{ ok: boolean }> {
    return this.request('/admin/auth/logout', { method: 'POST' });
  }

  static getMe(): Promise<AdminMe> {
    return this.request('/admin/auth/me');
  }

  // ── Seasons & Sets ────────────────────────────────────────────────────

  static getSeasons(): Promise<number[]> {
    return this.request('/admin/sets/seasons');
  }

  static getSetsBySeason(seasonId: number): Promise<AdminSet[]> {
    return this.request(`/admin/sets/seasons/${seasonId}`);
  }

  static createSet(seasonId: number, data: AdminSetCreate): Promise<AdminSet> {
    return this.request(`/admin/sets/seasons/${seasonId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  static updateSet(seasonId: number, setId: number, data: AdminSetUpdate): Promise<AdminSet> {
    return this.request(`/admin/sets/seasons/${seasonId}/${setId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  static regenerateSetIcon(seasonId: number, setId: number): Promise<AdminSet> {
    return this.request(`/admin/sets/seasons/${seasonId}/${setId}/regenerate-icon`, {
      method: 'POST',
    });
  }

  static deleteSet(seasonId: number, setId: number): Promise<void> {
    return this.request(`/admin/sets/seasons/${seasonId}/${setId}`, { method: 'DELETE' });
  }

  // ── Aspect Definitions ────────────────────────────────────────────────

  static getAspectDefs(setId: number, seasonId: number): Promise<AdminAspectDef[]> {
    return this.request(`/admin/aspects/sets/${setId}/season/${seasonId}`);
  }

  static createAspectDef(data: AdminAspectDefCreate): Promise<AdminAspectDef> {
    return this.request('/admin/aspects', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  static updateAspectDef(defId: number, data: AdminAspectDefUpdate): Promise<AdminAspectDef> {
    return this.request(`/admin/aspects/${defId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  static deleteAspectDef(defId: number): Promise<void> {
    return this.request(`/admin/aspects/${defId}`, { method: 'DELETE' });
  }

  /** Bulk-upsert aspect defs by (name + set_id + season_id). Returns upserted count. */
  static bulkUpsertAspectDefs(
    seasonId: number,
    items: BulkAspectDefItem[],
  ): Promise<{ upserted: number }> {
    return this.request('/admin/aspects/bulk', {
      method: 'POST',
      body: JSON.stringify({
        season_id: seasonId,
        definitions: items.map((i) => ({ set_id: i.set_id, name: i.name, rarity: i.rarity })),
      }),
    });
  }

  static getAspectDefStats(defId: number): Promise<{ owned_count: number }> {
    return this.request(`/admin/aspects/${defId}/stats`);
  }

  // ── Aspect Types ──────────────────────────────────────────────────────

  static getTypes(): Promise<AdminAspectType[]> {
    return this.request('/admin/types');
  }

  static getAspectsByType(typeId: number): Promise<AdminAspectByType[]> {
    return this.request(`/admin/types/${typeId}/aspects`);
  }

  static createType(data: AdminAspectTypeCreate): Promise<AdminAspectType> {
    return this.request('/admin/types', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  static updateType(typeId: number, data: AdminAspectTypeUpdate): Promise<AdminAspectType> {
    return this.request(`/admin/types/${typeId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  static deleteType(typeId: number): Promise<void> {
    return this.request(`/admin/types/${typeId}`, { method: 'DELETE' });
  }
}
