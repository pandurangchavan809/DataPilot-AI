import { ChevronLeft, ChevronRight, Download, Table2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { downloadText, formatCell, formatDuration, toCsv } from "@/lib/format";
import type { QueryResult } from "@/types/api";

const PAGE_SIZE = 10;

export function ResultTable({ result }: { result: QueryResult }) {
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(result.rows.length / PAGE_SIZE));
  const rows = result.rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const numeric = result.column_types.map((t) => t === "number");

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
      <div className="flex items-center gap-2 border-b border-zinc-200 bg-zinc-50 px-3.5 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
        <Table2 className="h-4 w-4 text-zinc-500" />
        <span className="text-[13px] font-medium">
          {result.row_count.toLocaleString()} {result.row_count === 1 ? "row" : "rows"}
        </span>
        <span className="text-xs text-zinc-500">· {formatDuration(result.elapsed_ms)}</span>
        {result.truncated && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
            limited
          </span>
        )}
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto"
          disabled={!result.rows.length}
          onClick={() => downloadText(`datapilot-${Date.now()}.csv`, toCsv(result.columns, result.rows))}
        >
          <Download className="h-3.5 w-3.5" /> CSV
        </Button>
      </div>

      {result.rows.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-zinc-500">The query returned no rows.</p>
      ) : (
        <div className="max-h-[420px] overflow-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead className="sticky top-0 z-10 bg-white dark:bg-zinc-950">
              <tr>
                {result.columns.map((c, i) => (
                  <th
                    key={c + i}
                    className={cn(
                      "border-b border-zinc-200 px-3.5 py-2 font-medium whitespace-nowrap text-zinc-500 dark:border-zinc-800",
                      numeric[i] ? "text-right" : "text-left",
                    )}
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, r) => (
                <tr key={r} className="hover:bg-zinc-50 dark:hover:bg-zinc-900/60">
                  {row.map((v, i) => (
                    <td
                      key={i}
                      className={cn(
                        "max-w-[320px] truncate border-b border-zinc-100 px-3.5 py-2 dark:border-zinc-800/60",
                        numeric[i] ? "text-right font-mono text-[12.5px] tabular-nums" : "",
                        v === null && "text-zinc-400 italic",
                      )}
                      title={formatCell(v)}
                    >
                      {formatCell(v)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pages > 1 && (
        <div className="flex items-center justify-between border-t border-zinc-200 px-3.5 py-1.5 text-xs text-zinc-500 dark:border-zinc-800">
          <span>
            Page {page + 1} of {pages}
          </span>
          <div className="flex gap-1">
            <Button variant="ghost" size="icon" disabled={page === 0} onClick={() => setPage((p) => p - 1)} aria-label="Previous page">
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)} aria-label="Next page">
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
