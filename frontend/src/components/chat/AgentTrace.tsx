import {
  BarChart3,
  Check,
  ChevronDown,
  CircleSlash,
  Code2,
  Compass,
  Database,
  Loader2,
  MessageSquare,
  Play,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { useState, type ComponentType } from "react";

import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import type { AgentStep } from "@/types/api";
import type { AssistantStatus } from "@/types/chat";

const KIND_ICONS: Record<string, ComponentType<{ className?: string }>> = {
  route: Compass,
  schema: Database,
  sql: Code2,
  guard: ShieldCheck,
  execute: Play,
  chart: BarChart3,
  insight: Sparkles,
  answer: MessageSquare,
};

function StatusIcon({ status }: { status: AgentStep["status"] }) {
  if (status === "running") return <Loader2 className="h-3.5 w-3.5 animate-spin text-brand-500" />;
  if (status === "error") return <TriangleAlert className="h-3.5 w-3.5 text-amber-500" />;
  if (status === "skipped") return <CircleSlash className="h-3.5 w-3.5 text-zinc-400" />;
  return <Check className="h-3.5 w-3.5 text-emerald-500" />;
}

export function AgentTrace({ steps, status }: { steps: AgentStep[]; status: AssistantStatus }) {
  const [open, setOpen] = useState<boolean | null>(null);
  if (!steps.length) {
    return status === "streaming" ? (
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <Loader2 className="h-4 w-4 animate-spin text-brand-500" />
        <span className="shimmer-text">Starting agents…</span>
      </div>
    ) : null;
  }

  const running = steps.find((s) => s.status === "running");
  const total = steps.reduce((sum, s) => sum + (s.duration_ms ?? 0), 0);
  const issues = steps.filter((s) => s.status === "error").length;
  // Live-expanded while streaming, collapsed afterwards, unless the user toggled it.
  const expanded = open ?? status === "streaming";

  return (
    <div className="rounded-xl border border-zinc-200/80 bg-zinc-50/60 dark:border-zinc-800 dark:bg-zinc-900/40">
      <button
        onClick={() => setOpen(!expanded)}
        className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13px]"
        aria-expanded={expanded}
      >
        {running ? (
          <>
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-brand-500" />
            <span className="shimmer-text font-medium text-zinc-700 dark:text-zinc-300">{running.label}…</span>
          </>
        ) : (
          <>
            <Sparkles className="h-4 w-4 shrink-0 text-brand-500" />
            <span className="font-medium text-zinc-700 dark:text-zinc-300">
              {status === "stopped" ? "Stopped" : "Reasoned"} in {formatDuration(total)}
            </span>
            <span className="text-zinc-400">·</span>
            <span className="text-zinc-500">
              {steps.length} {steps.length === 1 ? "step" : "steps"}{issues ? `, ${issues} self-corrected` : ""}
            </span>
          </>
        )}
        <ChevronDown className={cn("ml-auto h-4 w-4 shrink-0 text-zinc-400 transition-transform", expanded && "rotate-180")} />
      </button>

      {expanded && (
        <ol className="relative space-y-0.5 border-t border-zinc-200/80 px-3.5 py-3 dark:border-zinc-800">
          {steps.map((step, i) => {
            const Icon = KIND_ICONS[step.kind] ?? Sparkles;
            return (
              <li key={step.id} className="relative flex gap-3 pb-2 animate-fade-in">
                {i < steps.length - 1 && (
                  <span className="absolute top-7 bottom-0 left-[13px] w-px bg-zinc-200 dark:bg-zinc-800" aria-hidden />
                )}
                <span className="relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-zinc-200 bg-white dark:border-zinc-700 dark:bg-zinc-900">
                  <Icon className="h-3.5 w-3.5 text-zinc-500 dark:text-zinc-400" />
                </span>
                <div className="min-w-0 flex-1 pt-1">
                  <div className="flex items-center gap-2 text-[13px]">
                    <StatusIcon status={step.status} />
                    <span className="font-medium text-zinc-800 dark:text-zinc-200">{step.label}</span>
                    {step.duration_ms !== undefined && step.status !== "running" && (
                      <span className="ml-auto shrink-0 font-mono text-[11px] text-zinc-400">
                        {formatDuration(step.duration_ms)}
                      </span>
                    )}
                  </div>
                  {step.detail && (
                    <p
                      className={cn(
                        "mt-0.5 text-xs leading-5 break-words",
                        step.status === "error" ? "text-amber-600 dark:text-amber-400" : "text-zinc-500",
                      )}
                    >
                      {step.detail}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
