import useAuthStore from "@/stores/authStore";

// Use relative URLs so requests are proxied through Next.js rewrites,
// avoiding cross-origin (CORS) issues in production.
const API_BASE = "";

/**
 * Authenticated fetch wrapper.
 * - Attaches Bearer token from auth store
 * - On 401, attempts refresh + retry once
 * - On refresh failure, calls logout()
 */
export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const store = useAuthStore.getState();
  const headers = new Headers(init?.headers);

  if (store.accessToken) {
    headers.set("Authorization", `Bearer ${store.accessToken}`);
  }

  let res = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (res.status === 401 && store.accessToken) {
    // Try refreshing the token
    const refreshed = await store.refresh();
    if (refreshed) {
      const newStore = useAuthStore.getState();
      headers.set("Authorization", `Bearer ${newStore.accessToken}`);
      res = await fetch(`${API_BASE}${path}`, { ...init, headers });
    } else {
      await store.logout();
    }
  }

  return res;
}
