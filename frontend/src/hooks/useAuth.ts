import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";

import { api, onAuthChange, setTokens } from "@/api";
import { useApp } from "@/hooks/useApp";
import type { AuthResponse, AuthTokens, AuthUser } from "@/types";

/** Demo account seeded by the backend, shown on the login page for reviewers. */
export const DEMO_ACCOUNT = { email: "user", password: "User@1234" };

/** localStorage that never throws, so login survives a reload and works across tabs. */
const safeLocalStorage: StateStorage = {
  getItem: (k) => {
    try {
      return localStorage.getItem(k);
    } catch {
      return null;
    }
  },
  setItem: (k, v) => {
    try {
      localStorage.setItem(k, v);
    } catch {
      /* storage unavailable: stay logged in for this page only */
    }
  },
  removeItem: (k) => {
    try {
      localStorage.removeItem(k);
    } catch {
      /* ignore */
    }
  },
};

interface AuthState {
  user: AuthUser | null;
  tokens: AuthTokens | null;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuth = create<AuthState>()(
  persist(
    (set, get) => {
      const accept = (res: AuthResponse) => {
        const tokens = { access_token: res.access_token, refresh_token: res.refresh_token };
        setTokens(tokens);
        set({ user: res.user, tokens });
      };
      return {
        user: null,
        tokens: null,
        login: async (email, password) => accept(await api.login(email, password)),
        signup: async (email, password) => accept(await api.signup(email, password)),
        logout: async () => {
          await api.disconnect().catch(() => {}); // close this user's DB session
          const refresh = get().tokens?.refresh_token; // read after: disconnect may have rotated it
          if (refresh) await api.logout(refresh).catch(() => {});
          setTokens(null);
          set({ user: null, tokens: null });
          useApp.getState().reset(); // the next user must not see this user's chat
        },
      };
    },
    {
      name: "datapilot-auth",
      storage: createJSONStorage(() => safeLocalStorage),
      partialize: (s) => ({ user: s.user, tokens: s.tokens }),
      onRehydrateStorage: () => (state) => setTokens(state?.tokens ?? null),
    },
  ),
);

setTokens(useAuth.getState().tokens);

// Keep the store in sync when api.ts refreshes tokens (or gives up and logs out).
onAuthChange((tokens) => {
  if (tokens) useAuth.setState({ tokens });
  else {
    useAuth.setState({ user: null, tokens: null });
    useApp.getState().reset();
  }
});

// Another tab logged in, out, or refreshed: pick up its tokens so this tab never
// sends an already-rotated refresh token (the server would treat that as theft).
window.addEventListener("storage", (e) => {
  if (e.key === "datapilot-auth") void useAuth.persist.rehydrate();
});
