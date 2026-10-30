import { Database, LogOut, Moon, PlugZap, RefreshCw, SquarePen, Sun, Unplug, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Logo } from "@/components/ui/Logo";
import { useConnection } from "@/hooks/useConnection";
import { cn, displayName, initials } from "@/utils";
import { useApp } from "@/hooks/useApp";
import { useAuth } from "@/hooks/useAuth";

import { SchemaExplorer } from "./SchemaExplorer";

const DIALECT_LABEL: Record<string, string> = { sqlite: "SQLite", postgres: "PostgreSQL", mysql: "MySQL" };

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("dp-theme", dark ? "dark" : "light");
    } catch {
      /* storage unavailable */
    }
  }, [dark]);
  return { dark, toggle: () => setDark((d) => !d) };
}

function UserCard() {
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);
  if (!user) return null;
  const isEmail = user.email.includes("@");
  return (
    <div className="mx-3 mt-3 flex items-center gap-2.5 rounded-xl px-1.5 py-1">
      <span
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-accent-500 text-xs font-semibold text-white"
        aria-hidden
      >
        {initials(user.email)}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium" title={user.email}>{displayName(user.email)}</p>
        <p className="truncate text-xs text-zinc-500">{isEmail ? user.email : "Demo account"}</p>
      </div>
      <Button variant="ghost" size="icon" onClick={logout} aria-label="Log out" title="Log out">
        <LogOut className="h-4 w-4" />
      </Button>
    </div>
  );
}

export function Sidebar() {
  const open = useApp((s) => s.sidebarOpen);
  const setOpen = useApp((s) => s.setSidebarOpen);
  const connection = useApp((s) => s.connection.connection);
  const newChat = useApp((s) => s.newChat);
  const setConnectOpen = useApp((s) => s.setConnectOpen);
  const { disconnect, refresh, pending } = useConnection();
  const { dark, toggle } = useTheme();

  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-zinc-950/40 lg:hidden" onClick={() => setOpen(false)} />}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[280px] flex-col border-r border-zinc-200 bg-zinc-50 transition-transform duration-200 lg:static lg:translate-x-0 dark:border-zinc-800/80 dark:bg-zinc-900/50",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex items-center gap-2.5 px-4 pt-4 pb-3">
          <Logo />
          <span className="text-[15px] font-semibold tracking-tight">DataPilot</span>
          <span className="rounded-md bg-zinc-200/70 px-1.5 py-0.5 text-[10px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">AI</span>
          <Button variant="ghost" size="icon" className="ml-auto lg:hidden" onClick={() => setOpen(false)} aria-label="Close sidebar">
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="px-3">
          <Button variant="secondary" className="w-full justify-start" onClick={() => (newChat(), setOpen(false))}>
            <SquarePen className="h-4 w-4" /> New chat
          </Button>
        </div>

        <UserCard />

        <div className="mx-3 mt-4 mb-3 rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
          {connection ? (
            <>
              <div className="flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                </span>
                <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400">Connected · read-only</span>
              </div>
              <p className="mt-2 truncate text-sm font-medium" title={connection.name}>{connection.name}</p>
              <p className="text-xs text-zinc-500">{DIALECT_LABEL[connection.dialect] ?? connection.dialect}</p>
              <div className="mt-3 flex gap-1">
                <Button variant="ghost" size="sm" onClick={() => setConnectOpen(true)}>
                  <PlugZap className="h-3.5 w-3.5" /> Switch
                </Button>
                <Button variant="ghost" size="sm" onClick={refresh} disabled={pending} aria-label="Refresh schema">
                  <RefreshCw className={cn("h-3.5 w-3.5", pending && "animate-spin")} />
                </Button>
                <Button variant="danger" size="sm" className="ml-auto" onClick={disconnect} aria-label="Disconnect">
                  <Unplug className="h-3.5 w-3.5" />
                </Button>
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 text-sm font-medium">
                <Database className="h-4 w-4 text-zinc-400" /> No database
              </div>
              <p className="mt-1 text-xs leading-5 text-zinc-500">Connect a database or load the demo to start.</p>
              <Button variant="primary" size="sm" className="mt-3 w-full" onClick={() => setConnectOpen(true)}>
                <PlugZap className="h-3.5 w-3.5" /> Connect
              </Button>
            </>
          )}
        </div>

        <SchemaExplorer />

        <div className="mt-auto flex items-center justify-between border-t border-zinc-200 px-4 py-3 text-xs text-zinc-500 dark:border-zinc-800">
          <span>Chats stay in this tab only</span>
          <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </aside>
    </>
  );
}
