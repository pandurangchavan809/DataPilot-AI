import { useCallback, useState } from "react";

import { api, ApiError } from "@/api";
import { useApp } from "@/hooks/useApp";
import type { ConnectPayload } from "@/types";

export function useConnection() {
  const setConnection = useApp((s) => s.setConnection);
  const newChat = useApp((s) => s.newChat);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connect = useCallback(
    async (payload: ConnectPayload) => {
      setPending(true);
      setError(null);
      try {
        const state = await api.connect(payload);
        const previous = useApp.getState().connection.connection;
        setConnection(state);
        // A different database invalidates the conversation context.
        if (previous && previous.name !== state.connection?.name) newChat();
        return true;
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Connection failed.");
        return false;
      } finally {
        setPending(false);
      }
    },
    [setConnection, newChat],
  );

  const disconnect = useCallback(async () => {
    try {
      await api.disconnect();
    } finally {
      setConnection({ connection: null, schema: null });
    }
  }, [setConnection]);

  const refresh = useCallback(async () => {
    setPending(true);
    try {
      setConnection(await api.refreshSchema());
    } catch (err) {
      if (err instanceof ApiError && err.code === "not_connected") setConnection({ connection: null, schema: null });
    } finally {
      setPending(false);
    }
  }, [setConnection]);

  return { connect, disconnect, refresh, pending, error, setError };
}
