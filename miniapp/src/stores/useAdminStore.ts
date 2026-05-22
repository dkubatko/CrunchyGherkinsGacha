import { create } from 'zustand';
import { AdminApiService } from '../services/adminApi';

interface AdminAuthState {
  username: string | null;
  isAuthenticated: boolean;
  setAuth: (username: string) => void;
  logout: () => Promise<void>;
  clearAuth: () => void;
}

export const useAdminStore = create<AdminAuthState>((set) => ({
  username: null,
  isAuthenticated: false,

  setAuth: (username) => {
    // Username is non-sensitive and survives reloads via /me; we cache it in
    // localStorage purely so the header shows the right name before /me returns.
    try {
      localStorage.setItem('admin_username', username);
    } catch {
      /* ignore storage errors (private mode, etc.) */
    }
    set({ username, isAuthenticated: true });
  },

  logout: async () => {
    try {
      await AdminApiService.logout();
    } catch {
      // Best-effort: even if the server call fails, clear local state.
    }
    try {
      localStorage.removeItem('admin_username');
    } catch {
      /* ignore */
    }
    set({ username: null, isAuthenticated: false });
  },

  clearAuth: () => {
    try {
      localStorage.removeItem('admin_username');
    } catch {
      /* ignore */
    }
    set({ username: null, isAuthenticated: false });
  },
}));
