import { ChevronRight, Eye, KeyRound, Link2, Search, Table2 } from "lucide-react";
import { useMemo, useState } from "react";

import { cn } from "@/lib/cn";
import { useApp } from "@/store/app";

export function SchemaExplorer() {
  const schema = useApp((s) => s.connection.schema);
  const setDraft = useApp((s) => s.setDraft);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});

  const tables = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!schema) return [];
    if (!q) return schema.tables;
    return schema.tables.filter(
      (t) => t.name.toLowerCase().includes(q) || t.columns.some((c) => c.name.toLowerCase().includes(q)),
    );
  }, [schema, query]);

  if (!schema) return null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between px-3 pt-1 pb-2">
        <span className="text-[11px] font-medium tracking-wide text-zinc-400 uppercase">Schema</span>
        <span className="text-[11px] text-zinc-400">{schema.tables.length} tables</span>
      </div>
      {schema.tables.length > 6 && (
        <div className="relative mx-2 mb-2">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter tables & columns"
            className="h-8 w-full rounded-lg border border-zinc-200 bg-white pr-2 pl-8 text-xs outline-none focus:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-900"
          />
        </div>
      )}
      <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {tables.map((t) => {
          const isOpen = open[t.name] ?? !!query;
          const fkCols = new Set(t.foreign_keys.flatMap((f) => f.columns));
          return (
            <li key={t.name}>
              <div className="group flex items-center rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800/60">
                <button
                  onClick={() => setOpen((o) => ({ ...o, [t.name]: !isOpen }))}
                  className="flex min-w-0 flex-1 items-center gap-1.5 px-2 py-1.5 text-left text-[13px]"
                  aria-expanded={isOpen}
                >
                  <ChevronRight className={cn("h-3.5 w-3.5 shrink-0 text-zinc-400 transition-transform", isOpen && "rotate-90")} />
                  {t.is_view ? <Eye className="h-3.5 w-3.5 shrink-0 text-zinc-400" /> : <Table2 className="h-3.5 w-3.5 shrink-0 text-zinc-400" />}
                  <span className="truncate font-medium text-zinc-700 dark:text-zinc-300">{t.name}</span>
                  <span className="ml-auto shrink-0 text-[11px] text-zinc-400">{t.columns.length}</span>
                </button>
                <button
                  onClick={() => setDraft(`Give me an overview of the ${t.name} table`)}
                  className="mr-1 hidden rounded-md px-1.5 py-0.5 text-[11px] text-brand-600 group-hover:block hover:bg-brand-50 dark:text-brand-400 dark:hover:bg-brand-500/10"
                >
                  Ask
                </button>
              </div>
              {isOpen && (
                <ul className="mt-0.5 mb-1 ml-[22px] border-l border-zinc-200 pl-2 dark:border-zinc-800">
                  {t.columns.map((c) => (
                    <li key={c.name} className="flex items-center gap-1.5 py-1 pr-2 text-xs" title={`${c.name} · ${c.type}`}>
                      {c.primary_key ? (
                        <KeyRound className="h-3 w-3 shrink-0 text-amber-500" />
                      ) : fkCols.has(c.name) ? (
                        <Link2 className="h-3 w-3 shrink-0 text-brand-500" />
                      ) : (
                        <span className="w-3 shrink-0" />
                      )}
                      <span className="truncate text-zinc-600 dark:text-zinc-400">{c.name}</span>
                      <span className="ml-auto shrink-0 font-mono text-[10px] text-zinc-400 uppercase">{c.type.split("(")[0].toLowerCase()}</span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
        {!tables.length && <li className="px-3 py-4 text-center text-xs text-zinc-400">No matches</li>}
      </ul>
    </div>
  );
}
