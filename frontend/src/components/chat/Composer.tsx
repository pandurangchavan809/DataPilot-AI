import { ArrowUp, Lock, Square } from "lucide-react";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/cn";
import { useApp } from "@/store/app";

interface ComposerProps {
  busy: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export function Composer({ busy, onSend, onStop }: ComposerProps) {
  const draft = useApp((s) => s.draft);
  const setDraft = useApp((s) => s.setDraft);
  const connected = useApp((s) => !!s.connection.connection);
  const maxChars = useApp((s) => s.config?.limits.max_message_chars ?? 4000);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [draft]);

  useEffect(() => {
    if (connected) ref.current?.focus();
  }, [connected]);

  const tooLong = draft.length > maxChars;
  const canSend = connected && !busy && draft.trim().length > 0 && !tooLong;

  const submit = () => {
    if (!canSend) return;
    onSend(draft);
    setDraft("");
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-4 sm:px-6">
      <div
        className={cn(
          "rounded-2xl border bg-white shadow-[0_2px_16px_-6px_rgb(0_0_0/0.12)] transition-colors focus-within:border-zinc-400 dark:bg-zinc-900 dark:focus-within:border-zinc-600",
          tooLong ? "border-red-400" : "border-zinc-200 dark:border-zinc-800",
        )}
      >
        <textarea
          ref={ref}
          rows={1}
          value={draft}
          disabled={!connected}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={connected ? "Ask anything about your data…" : "Connect a database to start asking questions"}
          className="block max-h-[220px] w-full resize-none bg-transparent px-4 pt-3.5 pb-1 text-[15px] leading-6 outline-none placeholder:text-zinc-400 disabled:cursor-not-allowed"
          aria-label="Message"
        />
        <div className="flex items-center gap-2 px-3 pb-2.5">
          <span className="flex items-center gap-1 text-[11px] text-zinc-400">
            <Lock className="h-3 w-3" /> Read-only
          </span>
          {draft.length > maxChars * 0.8 && (
            <span className={cn("text-[11px] tabular-nums", tooLong ? "text-red-500" : "text-zinc-400")}>
              {draft.length}/{maxChars}
            </span>
          )}
          {busy ? (
            <button
              onClick={onStop}
              className="ml-auto flex h-8 w-8 items-center justify-center rounded-full bg-zinc-900 text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900"
              aria-label="Stop generating"
            >
              <Square className="h-3 w-3 fill-current" />
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={!canSend}
              className="ml-auto flex h-8 w-8 items-center justify-center rounded-full bg-zinc-900 text-white transition hover:bg-zinc-700 disabled:bg-zinc-200 disabled:text-zinc-400 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200 dark:disabled:bg-zinc-800 dark:disabled:text-zinc-600"
              aria-label="Send message"
            >
              <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
            </button>
          )}
        </div>
      </div>
      <p className="mt-2 text-center text-[11px] text-zinc-400">
        DataPilot can make mistakes. Verify important numbers against the SQL shown.
      </p>
    </div>
  );
}
