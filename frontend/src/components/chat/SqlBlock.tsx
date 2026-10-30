import { Check, ChevronDown, Code2, Copy } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";

import { cn } from "@/utils";

const TOKEN = new RegExp(
  [
    String.raw`(--[^\n]*)`,
    String.raw`('(?:[^']|'')*')`,
    String.raw`("(?:[^"]|"")*"|` + "`[^`]*`" + String.raw`)`,
    String.raw`\b(\d+(?:\.\d+)?)\b`,
    String.raw`\b(SELECT|FROM|WHERE|AND|OR|NOT|IN|IS|NULL|AS|ON|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|CROSS|GROUP|BY|ORDER|HAVING|LIMIT|OFFSET|WITH|UNION|ALL|DISTINCT|CASE|WHEN|THEN|ELSE|END|ASC|DESC|BETWEEN|LIKE|ILIKE|EXISTS|OVER|PARTITION|ROWS|CAST|INTERVAL|TRUE|FALSE)\b`,
    String.raw`\b([A-Za-z_][A-Za-z0-9_]*)(?=\s*\()`,
  ].join("|"),
  "gi",
);

const CLASSES = [
  "text-zinc-400 italic",
  "text-emerald-600 dark:text-emerald-400",
  "text-amber-700 dark:text-amber-300",
  "text-orange-600 dark:text-orange-300",
  "text-brand-600 font-medium dark:text-brand-400",
  "text-cyan-700 dark:text-cyan-300",
];

function highlight(sql: string) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of sql.matchAll(TOKEN)) {
    const idx = m.index ?? 0;
    if (idx > last) parts.push(sql.slice(last, idx));
    const group = m.slice(1).findIndex((g) => g !== undefined);
    parts.push(
      <span key={idx} className={CLASSES[group]}>
        {m[0]}
      </span>,
    );
    last = idx + m[0].length;
  }
  parts.push(sql.slice(last));
  return parts;
}

/** Light formatting: break before major clauses for readability. */
function pretty(sql: string) {
  if (sql.includes("\n")) return sql;
  return sql
    .replace(/\s+(FROM|WHERE|GROUP BY|ORDER BY|HAVING|LIMIT|UNION(?: ALL)?|(?:LEFT |RIGHT |INNER |FULL |CROSS )?JOIN)\b/gi, "\n$1")
    .trim();
}

export function SqlBlock({ sql, explanation }: { sql: string; explanation?: string }) {
  const [open, setOpen] = useState(true);
  const [copied, setCopied] = useState(false);
  const formatted = useMemo(() => pretty(sql), [sql]);
  const nodes = useMemo(() => highlight(formatted), [formatted]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
      <div className="flex items-center gap-2 border-b border-zinc-200 bg-zinc-50 px-3.5 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
        <button onClick={() => setOpen((v) => !v)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
          <Code2 className="h-4 w-4 shrink-0 text-zinc-500" />
          <span className="shrink-0 text-[13px] font-medium whitespace-nowrap">SQL query</span>
          {explanation && <span className="hidden truncate text-xs text-zinc-500 sm:inline">· {explanation}</span>}
          <ChevronDown className={cn("ml-auto h-4 w-4 shrink-0 text-zinc-400 transition-transform", open && "rotate-180")} />
        </button>
        <button
          onClick={copy}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-200/60 hover:text-zinc-800 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          aria-label="Copy SQL"
        >
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      {open && (
        <pre className="overflow-x-auto bg-white px-4 py-3.5 font-mono text-[12.5px] leading-6 text-zinc-800 dark:bg-zinc-950 dark:text-zinc-200">
          <code>{nodes}</code>
        </pre>
      )}
    </div>
  );
}
