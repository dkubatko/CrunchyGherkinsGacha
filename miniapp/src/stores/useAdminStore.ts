import { create } from 'zustand';

interface AdminAuthState {
  token: string | null;
  username: string | null;
  isAuthenticated: boolean;
  setAuth: (token: string, username: string) => void;
  logout: () => void;
  initialize: () => void;
}

export const useAdminStore = create<AdminAuthState>((set) => ({
  token: null,
  username: null,
  isAuthenticated: false,

  setAuth: (token, username) => {
    localStorage.setItem('admin_token', token);
    localStorage.setItem('admin_username', username);
    set({ token, username, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_username');
    set({ token: null, username: null, isAuthenticated: false });
  },

  initialize: () => {
    const token = localStorage.getItem('admin_token');
    const username = localStorage.getItem('admin_username');
    if (token && username) {
      set({ token, username, isAuthenticated: true });
    }
  },
}));
