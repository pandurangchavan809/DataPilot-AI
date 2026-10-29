import { ArrowRight, BarChart3, Database, Globe2, LineChart, PlugZap, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Logo } from "@/components/ui/Logo";
import { useApp } from "@/store/app";

const DEMO_SUGGESTIONS = [
  { icon: TrendingUp, text: "Which 10 countries have the highest GDP per capita?" },
  { icon: BarChart3, text: "Plot total GDP by continent as a bar chart" },
  { icon: Globe2, text: "Compare literacy rate and AI startups for Asian countries" },
  { icon: LineChart, text: "Which countries earn the most from tourism relative to GDP?" },
];

const GENERIC_SUGGESTIONS = [
  { icon: Database, text: "What data is available in this database?" },
  { icon: TrendingUp, text: "Show the 10 largest records by value in the main table" },
  { icon: BarChart3, text: "Chart the number of records per category" },
  { icon: Sparkles, text: "Summarise the key trends in this data" },
];

export function EmptyState({ onPick, onTryDemo, connecting }: { onPick: (t: string) => void; onTryDemo: () => void; connecting: boolean }) {
  const connection = useApp((s) => s.connection.connection);
  const setConnectOpen = useApp((s) => s.setConnectOpen);
  const suggestions = connection?.type === "sqlite_demo" ? DEMO_SUGGESTIONS : GENERIC_SUGGESTIONS;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center px-4 py-10 sm:px-6">
      <div className="relative mb-6">
        <div className="absolute inset-0 -z-10 scale-150 rounded-full bg-gradient-to-br from-brand-500/25 to-accent-500/25 blur-2xl" />
        <Logo className="h-12 w-12" />
      </div>
      <h1 className="text-center text-2xl font-semibold tracking-tight sm:text-3xl">
        {connection ? (
          <>
            What would you like to <span className="text-gradient">know</span>?
          </>
        ) : (
          <>
            Talk to your data in <span className="text-gradient">plain English</span>
          </>
        )}
      </h1>
      <p className="mt-3 max-w-lg text-center text-sm leading-6 text-zinc-500 dark:text-zinc-400">
        {connection
          ? `Connected to ${connection.name}. A team of agents will plan, write, verify and run read-only SQL, then explain the results.`
          : "Connect PostgreSQL, MySQL or try the demo database. Agents translate your questions into safe, read-only SQL, then explain and chart the results."}
      </p>

      {connection ? (
        <div className="mt-8 grid w-full gap-2.5 sm:grid-cols-2">
          {suggestions.map(({ icon: Icon, text }) => (
            <button
              key={text}
              onClick={() => onPick(text)}
              className="group flex items-start gap-3 rounded-2xl border border-zinc-200 bg-white p-4 text-left text-sm transition hover:border-zinc-300 hover:shadow-sm dark:border-zinc-800 dark:bg-zinc-900/50 dark:hover:border-zinc-700"
            >
              <Icon className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
              <span className="flex-1 text-zinc-700 dark:text-zinc-300">{text}</span>
              <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-zinc-300 transition group-hover:translate-x-0.5 group-hover:text-zinc-500" />
            </button>
          ))}
        </div>
      ) : (
        <div className="mt-8 flex flex-col gap-2.5 sm:flex-row">
          <Button variant="primary" onClick={onTryDemo} disabled={connecting}>
            <Sparkles className="h-4 w-4" /> {connecting ? "Loading demo…" : "Try the demo database"}
          </Button>
          <Button onClick={() => setConnectOpen(true)}>
            <PlugZap className="h-4 w-4" /> Connect your database
          </Button>
        </div>
      )}

      <div className="mt-10 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs text-zinc-400">
        <span className="flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5" /> Read-only, enforced 3 ways</span>
        <span className="flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5" /> Self-correcting SQL agents</span>
        <span className="flex items-center gap-1.5"><BarChart3 className="h-3.5 w-3.5" /> Charts on request</span>
      </div>
    </div>
  );
}
