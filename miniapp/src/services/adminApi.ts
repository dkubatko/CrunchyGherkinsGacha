import type {
  AdminSet,
  AdminModifier,
  AdminModifierCreate,
  AdminModifierUpdate,
  AdminSetCreate,
  AdminSetUpdate,
  AdminMe,
} from '../types/admin';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://api.crunchygherkins.com';

export class AdminApiService {
  private static getToken(): string | null {
    return localStorage.getItem('admin_token');
  }

  private static getHeaders(): HeadersInit {
    const headers: HeadersInit = { 'Content-Type': 'application/json' };
    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  }

  private static async handleResponse<T>(response: Response): Promise<T> {
    if (response.status === 401) {
      localStorage.removeItem('admin_token');
      localStorage.removeItem('admin_username');
      window.location.href = '/admin';
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
    return response.json();
  }

  // ── Auth ──────────────────────────────────────────────────────────────

  static async login(username: string, password: string): Promise<{ message: string }> {
    const res = await fetch(`${API_BASE_URL}/admin/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    return this.handleResponse(res);
  }

  static async verifyOtp(username: string, code: string): Promise<{ token: string }> {
    const res = await fetch(`${API_BASE_URL}/admin/auth/verify-otp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, code }),
    });
    return this.handleResponse(res);
  }

  static async getMe(): Promise<AdminMe> {
    const res = await fetch(`${API_BASE_URL}/admin/auth/me`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(res);
  }

  // ── Seasons & Sets ────────────────────────────────────────────────────

  static async getSeasons(): Promise<number[]> {
    const res = await fetch(`${API_BASE_URL}/admin/sets/seasons`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(res);
  }

  static async getSetsBySeason(seasonId: number): Promise<AdminSet[]> {
    const res = await fetch(`${API_BASE_URL}/admin/sets/seasons/${seasonId}`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(res);
  }

  static async createSet(seasonId: number, data: AdminSetCreate): Promise<AdminSet> {
    const res = await fetch(`${API_BASE_URL}/admin/sets/seasons/${seasonId}`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(data),
    });
    return this.handleResponse(res);
  }

  static async updateSet(seasonId: number, setId: number, data: AdminSetUpdate): Promise<AdminSet> {
    const res = await fetch(`${API_BASE_URL}/admin/sets/seasons/${seasonId}/${setId}`, {
      method: 'PUT',
      headers: this.getHeaders(),
      body: JSON.stringify(data),
    });
    return this.handleResponse(res);
  }

  // ── Modifiers ─────────────────────────────────────────────────────────

  static async getModifiers(setId: number, seasonId: number): Promise<AdminModifier[]> {
    const res = await fetch(`${API_BASE_URL}/admin/modifiers/sets/${setId}/season/${seasonId}`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(res);
  }

  static async createModifier(data: AdminModifierCreate): Promise<AdminModifier> {
    const res = await fetch(`${API_BASE_URL}/admin/modifiers`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(data),
    });
    return this.handleResponse(res);
  }

  static async updateModifier(modifierId: number, data: AdminModifierUpdate): Promise<AdminModifier> {
    const res = await fetch(`${API_BASE_URL}/admin/modifiers/${modifierId}`, {
      method: 'PUT',
      headers: this.getHeaders(),
      body: JSON.stringify(data),
    });
    return this.handleResponse(res);
  }

  static async deleteModifier(modifierId: number): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/admin/modifiers/${modifierId}`, {
      method: 'DELETE',
      headers: this.getHeaders(),
    });
    if (res.status === 401) {
      localStorage.removeItem('admin_token');
      localStorage.removeItem('admin_username');
      window.location.href = '/admin';
      throw new Error('Session expired.');
    }
    if (!res.ok) {
      let detail = `Delete failed (${res.status})`;
      try {
        const body = await res.json();
        if (body?.detail) detail = body.detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
  }

  static async getModifierStats(modifierId: number): Promise<{ card_count: number }> {
    const res = await fetch(`${API_BASE_URL}/admin/modifiers/${modifierId}/stats`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(res);
  }
}
