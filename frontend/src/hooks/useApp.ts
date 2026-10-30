import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";

import { setSessionId } from "@/api";
import { uid } from "@/utils";
import type { AssistantMessage, ChatMessage, ClientConfig, ConnectionState } from "@/types";

/** sessionStorage that never throws (private mode, quota exceeded, etc.). */
const safeSessionStorage: StateStorage = {
  getItem: (k) => {
    try {
      return sessionStorage.getItem(k);
    } catch {
      return null;
    }
  },
  setItem: (k, v) => {
    try {
      sessionStorage.setItem(k, v);
    } catch {
      /* ignore quota errors: chat continues in memory */
    }
  },
  removeItem: (k) => {
    try {
      sessionStorage.removeItem(k);
    } catch {
      /* ignore */
    }
  },
};

interface AppState {
  sessionId: string;
  messages: ChatMessage[];
  model: string;
  draft: string;

  config: ClientConfig | null;
  connection: ConnectionState;
  connectOpen: boolean;
  sidebarOpen: boolean;

  setConfig: (c: ClientConfig) => void;
  setConnection: (c: ConnectionState) => void;
  setConnectOpen: (open: boolean) => void;
  setSidebarOpen: (open: boolean) => void;
  setModel: (m: string) => void;
  setDraft: (d: string) => void;

  addMessage: (m: ChatMessage) => void;
  updateAssistant: (id: string, fn: (m: AssistantMessage) => AssistantMessage) => void;
  newChat: () => void;
  /** Wipe everything tied to the signed-in user (called on logout). */
  reset: () => void;
}

export const useApp = create<AppState>()(
  persist(
    (set) => ({
      sessionId: uid(),
      messages: [],
      model: "auto",
      draft: "",

      config: null,
      connection: { connection: null, schema: null },
      connectOpen: false,
      sidebarOpen: false,

      setConfig: (config) => set({ config }),
      setConnection: (connection) => set({ connection }),
      setConnectOpen: (connectOpen) => set({ connectOpen }),
      setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
      setModel: (model) => set({ model }),
      setDraft: (draft) => set({ draft }),

      addMessage: (m) => set((s) => ({ messages: [...s.messages, m] })),
      updateAssistant: (id, fn) =>
        set((s) => ({
          messages: s.messages.map((m) => (m.id === id && m.role === "assistant" ? fn(m) : m)),
        })),
      newChat: () => set({ messages: [], draft: "" }),
      reset: () => {
        const sessionId = uid();
        setSessionId(sessionId);
        set({ sessionId, messages: [], draft: "", connection: { connection: null, schema: null }, connectOpen: false });
      },
    }),
    {
      name: "datapilot-session",
      storage: createJSONStorage(() => safeSessionStorage),
      partialize: (s) => ({ sessionId: s.sessionId, messages: s.messages, model: s.model }),
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        // A reload interrupts any in-flight stream.
        state.messages = state.messages.map((m) =>
          m.role === "assistant" && m.status === "streaming" ? { ...m, status: "stopped" } : m,
        );
        setSessionId(state.sessionId);
      },
    },
  ),
);

setSessionId(useApp.getState().sessionId);
