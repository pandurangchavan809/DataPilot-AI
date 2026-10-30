import { useCallback, useRef, useState } from "react";

import { ApiError, streamChat } from "@/api";
import { uid } from "@/utils";
import { useApp } from "@/hooks/useApp";
import type { AgentStep, AssistantMessage, ChartSpec, QueryResult } from "@/types";

const HISTORY_MESSAGES = 12;

export function useChat() {
  const addMessage = useApp((s) => s.addMessage);
  const updateAssistant = useApp((s) => s.updateAssistant);
  const setConnection = useApp((s) => s.setConnection);
  const abortRef = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || abortRef.current) return;

      const { messages, model } = useApp.getState();
      const history = messages
        .filter((m) => m.role === "user" || (m.status === "done" && m.content))
        .slice(-HISTORY_MESSAGES)
        .map((m) => ({ role: m.role, content: m.content, sql: m.role === "assistant" ? m.sql?.sql ?? null : null }));

      addMessage({ id: uid(), role: "user", content: message, createdAt: Date.now() });
      const id = uid();
      addMessage({
        id,
        role: "assistant",
        content: "",
        status: "streaming",
        steps: [],
        models: [],
        createdAt: Date.now(),
      });
      const update = (fn: (m: AssistantMessage) => AssistantMessage) => updateAssistant(id, fn);

      const controller = new AbortController();
      abortRef.current = controller;
      setBusy(true);
      try {
        for await (const { event, data } of streamChat(
          { message, history, model: model === "auto" ? null : model },
          controller.signal,
        )) {
          switch (event) {
            case "step": {
              const step = data as AgentStep;
              update((m) => {
                const i = m.steps.findIndex((s) => s.id === step.id);
                const steps = i === -1 ? [...m.steps, step] : m.steps.map((s, j) => (j === i ? step : s));
                return { ...m, steps };
              });
              break;
            }
            case "token":
              update((m) => ({ ...m, content: m.content + (data as { text: string }).text }));
              break;
            case "sql":
              update((m) => ({ ...m, sql: data as AssistantMessage["sql"] }));
              break;
            case "result":
              update((m) => ({ ...m, result: data as QueryResult }));
              break;
            case "chart":
              update((m) => ({ ...m, chart: data as ChartSpec }));
              break;
            case "model":
              update((m) => ({ ...m, model: data as AssistantMessage["model"] }));
              break;
            case "error":
              update((m) => ({ ...m, status: "error", error: data as AssistantMessage["error"] }));
              break;
            case "done":
              update((m) => ({
                ...m,
                status: m.status === "error" ? "error" : "done",
                models: (data as { models: string[] }).models,
                finishedAt: Date.now(),
              }));
              break;
          }
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          update((m) => ({
            ...m,
            status: "stopped",
            finishedAt: Date.now(),
            steps: m.steps.map((s) => (s.status === "running" ? { ...s, status: "skipped" } : s)),
          }));
        } else {
          const e = err instanceof ApiError ? err : new ApiError("Unexpected error.", 0, "unknown");
          if (e.code === "not_connected") setConnection({ connection: null, schema: null });
          update((m) => ({ ...m, status: "error", error: { code: e.code, message: e.message }, finishedAt: Date.now() }));
        }
      } finally {
        update((m) =>
          m.status === "streaming" ? { ...m, status: "done", finishedAt: m.finishedAt ?? Date.now() } : m,
        );
        abortRef.current = null;
        setBusy(false);
      }
    },
    [addMessage, updateAssistant, setConnection],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  return { send, stop, busy };
}
