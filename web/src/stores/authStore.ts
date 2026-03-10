import { create } from "zustand";

const API_BASE = "";

export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
  auth_provider: string;
}

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  isLoading: boolean;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<boolean>;
  loadFromStorage: () => Promise<void>;
  setTokensFromOAuth: (accessToken: string, refreshToken: string, user: AuthUser) => void;
  getAuthHeaders: () => Record<string, string>;
}

const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken: null,
  isLoading: true,

  login: async (email, password) => {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Login failed");
    }
    const data = await res.json();
    localStorage.setItem("refresh_token", data.refresh_token);
    set({ user: data.user, accessToken: data.access_token, isLoading: false });
  },

  register: async (email, password, displayName) => {
    const res = await fetch(`${API_BASE}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, display_name: displayName || undefined }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Registration failed");
    }
    const data = await res.json();
    localStorage.setItem("refresh_token", data.refresh_token);
    set({ user: data.user, accessToken: data.access_token, isLoading: false });
  },

  logout: async () => {
    const { accessToken } = get();
    try {
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: "POST",
        headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
      });
    } catch {}
    localStorage.removeItem("refresh_token");
    set({ user: null, accessToken: null, isLoading: false });
  },

  refresh: async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) {
      set({ isLoading: false });
      return false;
    }
    try {
      const res = await fetch(`${API_BASE}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) {
        localStorage.removeItem("refresh_token");
        set({ user: null, accessToken: null, isLoading: false });
        return false;
      }
      const data = await res.json();
      localStorage.setItem("refresh_token", data.refresh_token);
      set({ user: data.user, accessToken: data.access_token, isLoading: false });
      return true;
    } catch {
      set({ isLoading: false });
      return false;
    }
  },

  loadFromStorage: async () => {
    set({ isLoading: true });
    await get().refresh();
  },

  setTokensFromOAuth: (accessToken, refreshToken, user) => {
    localStorage.setItem("refresh_token", refreshToken);
    set({ user, accessToken, isLoading: false });
  },

  getAuthHeaders: () => {
    const { accessToken } = get();
    return accessToken ? { Authorization: `Bearer ${accessToken}` } : ({} as Record<string, string>);
  },
}));

export default useAuthStore;
