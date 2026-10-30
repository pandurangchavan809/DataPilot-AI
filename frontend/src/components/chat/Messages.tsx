import { AlertCircle, Cpu, RotateCcw } from "lucide-react";
import { lazy, Suspense } from "react";

import { Logo } from "@/components/ui/Logo";
import { useApp } from "@/hooks/useApp";
import type { AssistantMessage as AssistantMsg, UserMessage as UserMsg } from "@/types";

import { AgentTrace } from "./AgentTrace";
import { Markdown } from "./Markdown";
import { ResultTable } from "./ResultTable";
import { SqlBlock } from "./SqlBlock";

// Recharts is the heaviest dependency; load it only when a chart is shown.
const ChartView = lazy(() => import("./ChartView").then((m) => ({ default: m.ChartView })));

export function UserMessage({ message }: { message: UserMsg }) {
  return (
    <div className="flex justify-end animate-fade-in">
      <div className="max-w-[85%] rounded-2xl rounded-br-md bg-zinc-100 px-4 py-2.5 text-[15px] leading-7 whitespace-pre-wrap text-zinc-900 dark:bg-zinc-800/80 dark:text-zinc-100">
        {message.content}
      </div>
    </div>
  );
}

export function AssistantMessage({ message, onRetry }: { message: AssistantMsg; onRetry?: () => void }) {
  const models = useApp((s) => s.config?.models);
  const streaming = message.status === "streaming";
  const modelLabels = message.models
    .map((id) => models?.find((m) => m.id === id)?.label ?? id.split(":").pop())
    .filter(Boolean);

  return (
    <div className="flex gap-3 animate-fade-in sm:gap-4">
      <Logo className="mt-0.5 h-7 w-7 shrink-0" />
      <div className="min-w-0 flex-1 space-y-4">
        <AgentTrace steps={message.steps} status={message.status} />

        {message.content && (
          <div>
            <Markdown text={message.content} />
            {streaming && message.steps.some((s) => s.status === "running" && (s.kind === "insight" || s.kind === "answer")) && (
              <span className="ml-0.5 inline-block h-4 w-[3px] translate-y-0.5 animate-blink rounded-sm bg-brand-500" />
            )}
          </div>
        )}

        {message.chart && message.result && (
          <Suspense fallback={<div className="h-[22rem] animate-pulse rounded-xl border border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/40" />}>
            <ChartView spec={message.chart} result={message.result} />
          </Suspense>
        )}
        {message.result && <ResultTable result={message.result} />}
        {message.sql && <SqlBlock sql={message.sql.sql} explanation={message.sql.explanation} />}

        {message.error && (
          <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <p className="flex-1 break-words">{message.error.message}</p>
            {onRetry && (
              <button onClick={onRetry} className="flex shrink-0 items-center gap-1 text-xs font-medium hover:underline">
                <RotateCcw className="h-3.5 w-3.5" /> Retry
              </button>
            )}
          </div>
        )}

        {message.status === "stopped" && <p className="text-xs text-zinc-500 italic">Generation stopped.</p>}

        {!streaming && modelLabels.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-400">
            <Cpu className="h-3 w-3" />
            {modelLabels.map((l) => (
              <span key={l} className="rounded-md bg-zinc-100 px-1.5 py-0.5 font-mono dark:bg-zinc-800/80">
                {l}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
