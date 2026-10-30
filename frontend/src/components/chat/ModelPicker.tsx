import { Check, ChevronDown, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/utils";
import { useApp } from "@/hooks/useApp";
import type { ModelInfo } from "@/types";

export function ModelPicker() {
  const config = useApp((s) => s.config);
  const model = useApp((s) => s.model);
  const setModel = useApp((s) => s.setModel);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  // Drop a stale selection if the server no longer offers it.
  useEffect(() => {
    if (config && model !== "auto" && !config.models.some((m) => m.id === model)) setModel("auto");
  }, [config, model, setModel]);

  if (!config) return null;
  const selected = config.models.find((m) => m.id === model);
  const groups = config.models.reduce<Record<string, ModelInfo[]>>((acc, m) => {
    (acc[m.provider_label] ??= []).push(m);
    return acc;
  }, {});

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex h-9 items-center gap-1.5 rounded-xl px-3 text-sm font-medium hover:bg-zinc-100 dark:hover:bg-zinc-800/70"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        {selected ? <span className="max-w-[180px] truncate">{selected.label}</span> : (
          <>
            <Sparkles className="h-4 w-4 text-brand-500" /> Auto
          </>
        )}
        <ChevronDown className="h-4 w-4 text-zinc-400" />
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute top-11 left-0 z-40 max-h-[70vh] w-[min(340px,calc(100vw-2rem))] overflow-y-auto rounded-2xl border border-zinc-200 bg-white p-1.5 shadow-xl animate-fade-in dark:border-zinc-800 dark:bg-zinc-900"
        >
          <Option
            active={model === "auto"}
            onClick={() => (setModel("auto"), setOpen(false))}
            title="Auto"
            subtitle="Primary, then secondary fallback"
            badge="Recommended"
          />
          {Object.entries(groups).map(([provider, items]) => (
            <div key={provider} className="mt-1.5">
              <p className="px-2.5 pt-1.5 pb-1 text-[11px] font-medium tracking-wide text-zinc-400 uppercase">{provider}</p>
              {items.map((m) => (
                <Option
                  key={m.id}
                  active={model === m.id}
                  onClick={() => (setModel(m.id), setOpen(false))}
                  title={m.label}
                  subtitle={m.name}
                  badge={m.roles.includes("primary") ? "Primary" : m.roles[0]}
                />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Option(props: { active: boolean; onClick: () => void; title: string; subtitle: string; badge?: string }) {
  return (
    <button
      role="option"
      aria-selected={props.active}
      onClick={props.onClick}
      className={cn(
        "flex w-full items-start gap-2.5 rounded-xl px-2.5 py-2 text-left hover:bg-zinc-100 dark:hover:bg-zinc-800",
        props.active && "bg-zinc-50 dark:bg-zinc-800/60",
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{props.title}</span>
          {props.badge && (
            <span className="shrink-0 rounded-md bg-brand-50 px-1.5 py-0.5 text-[10px] font-medium text-brand-600 capitalize dark:bg-brand-500/15 dark:text-brand-400">
              {props.badge}
            </span>
          )}
        </div>
        <p className="mt-0.5 truncate text-xs text-zinc-500">{props.subtitle}</p>
      </div>
      {props.active && <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />}
    </button>
  );
}
