import { ArrowDown, Menu, SquarePen } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { useChat } from "@/hooks/useChat";
import { useConnection } from "@/hooks/useConnection";
import { useApp } from "@/store/app";

import { Composer } from "./Composer";
import { EmptyState } from "./EmptyState";
import { AssistantMessage, UserMessage } from "./Messages";
import { ModelPicker } from "./ModelPicker";

export function ChatView() {
  const messages = useApp((s) => s.messages);
  const connection = useApp((s) => s.connection.connection);
  const setSidebarOpen = useApp((s) => s.setSidebarOpen);
  const newChat = useApp((s) => s.newChat);
  const { send, stop, busy } = useChat();
  const { connect, pending } = useConnection();

  const scrollRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);

  // Follow the stream only while the user is at the bottom.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && pinned) el.scrollTop = el.scrollHeight;
  }, [messages, pinned]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (el) setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  }, []);

  const sendAndPin = (text: string) => {
    setPinned(true);
    void send(text);
  };

  const retry = (index: number) => {
    const prev = messages[index - 1];
    if (prev?.role === "user") sendAndPin(prev.content);
  };

  return (
    <main className="flex min-w-0 flex-1 flex-col">
      <header className="flex h-14 shrink-0 items-center gap-1 border-b border-zinc-200/70 px-3 sm:px-4 dark:border-zinc-800/70">
        <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar">
          <Menu className="h-4 w-4" />
        </Button>
        <ModelPicker />
        <div className="ml-auto flex items-center gap-2">
          {connection && (
            <span className="hidden max-w-[240px] truncate rounded-full border border-zinc-200 px-2.5 py-1 text-xs text-zinc-500 sm:block dark:border-zinc-800">
              {connection.name}
            </span>
          )}
          {messages.length > 0 && (
            <Button variant="ghost" size="icon" onClick={newChat} aria-label="New chat" title="New chat">
              <SquarePen className="h-4 w-4" />
            </Button>
          )}
        </div>
      </header>

      <div ref={scrollRef} onScroll={onScroll} className="relative flex min-h-0 flex-1 flex-col overflow-y-auto">
        {messages.length === 0 ? (
          <EmptyState onPick={sendAndPin} onTryDemo={() => void connect({ type: "sqlite_demo" })} connecting={pending} />
        ) : (
          <div className="mx-auto w-full max-w-3xl space-y-8 px-4 py-8 sm:px-6">
            {messages.map((m, i) =>
              m.role === "user" ? (
                <UserMessage key={m.id} message={m} />
              ) : (
                <AssistantMessage key={m.id} message={m} onRetry={!busy && i === messages.length - 1 ? () => retry(i) : undefined} />
              ),
            )}
          </div>
        )}
      </div>

      <div className="relative">
        {!pinned && messages.length > 0 && (
          <button
            onClick={() => setPinned(true)}
            className="absolute -top-12 left-1/2 flex h-8 w-8 -translate-x-1/2 items-center justify-center rounded-full border border-zinc-200 bg-white shadow-md dark:border-zinc-700 dark:bg-zinc-900"
            aria-label="Scroll to bottom"
          >
            <ArrowDown className="h-4 w-4" />
          </button>
        )}
        <Composer busy={busy} onSend={sendAndPin} onStop={stop} />
      </div>
    </main>
  );
}
