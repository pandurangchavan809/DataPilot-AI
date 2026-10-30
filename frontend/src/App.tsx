import { AlertTriangle, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { ChatView } from "@/components/chat/ChatView";
import { ConnectionDialog } from "@/components/connection/ConnectionDialog";
import { Sidebar } from "@/components/sidebar/Sidebar";
import { Button } from "@/components/ui/Button";
import { api, ApiError } from "@/api";
import { useApp } from "@/hooks/useApp";

export default function App() {
  const setConfig = useApp((s) => s.setConfig);
  const setConnection = useApp((s) => s.setConnection);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");

  const boot = async () => {
    setStatus("loading");
    try {
      const [config, connection] = await Promise.all([api.config(), api.currentConnection()]);
      setConfig(config);
      setConnection(connection);
      setStatus("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load.");
      setStatus("error");
    }
  };

  useEffect(() => {
    void boot();
  }, []); // run once on mount

  if (status !== "ready") {
    return (
      <div className="flex h-full items-center justify-center p-6">
        {status === "loading" ? (
          <Loader2 className="h-6 w-6 animate-spin text-zinc-400" />
        ) : (
          <div className="max-w-sm text-center">
            <AlertTriangle className="mx-auto h-8 w-8 text-amber-500" />
            <p className="mt-3 font-medium">DataPilot is unavailable</p>
            <p className="mt-1 text-sm text-zinc-500">{error}</p>
            <Button className="mt-5" onClick={boot}>
              Try again
            </Button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar />
      <ChatView />
      <ConnectionDialog />
    </div>
  );
}
