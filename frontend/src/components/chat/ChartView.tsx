import { AreaChart as AreaIcon, BarChart3, LineChart as LineIcon, PieChart as PieIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, type TooltipProps, XAxis, YAxis } from "recharts";

import { cn, formatCell, formatCompact } from "@/utils";
import type { ChartSpec, ChartType, QueryResult } from "@/types";

// Fixed order, never cycled: identity follows the series, not its rank.
const SERIES = Array.from({ length: 8 }, (_, i) => `var(--series-${i + 1})`);
const MAX_PIE_SLICES = 8;

const AXIS = { stroke: "var(--chart-grid)", tick: { fill: "var(--chart-axis)", fontSize: 12 }, tickLine: false };

const SWITCHABLE: { type: ChartType; icon: typeof BarChart3; label: string }[] = [
  { type: "bar", icon: BarChart3, label: "Bar" },
  { type: "line", icon: LineIcon, label: "Line" },
  { type: "area", icon: AreaIcon, label: "Area" },
  { type: "pie", icon: PieIcon, label: "Pie" },
];

function ChartTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
      {label !== undefined && <p className="mb-1 font-medium text-zinc-900 dark:text-zinc-100">{String(label)}</p>}
      {payload.map((p) => (
        <div key={String(p.dataKey ?? p.name)} className="flex items-center gap-2 text-zinc-600 dark:text-zinc-300">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color ?? p.payload?.fill }} />
          <span>{p.name}</span>
          <span className="ml-auto pl-3 font-mono tabular-nums text-zinc-900 dark:text-zinc-100">{formatCell(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

/** Pie slices > 8 fold into "Other" rather than inventing a 9th hue. */
function pieData(data: Record<string, unknown>[], x: string, y: string) {
  const sorted = [...data].sort((a, b) => Number(b[y] ?? 0) - Number(a[y] ?? 0));
  if (sorted.length <= MAX_PIE_SLICES) return sorted;
  const head = sorted.slice(0, MAX_PIE_SLICES - 1);
  const other = sorted.slice(MAX_PIE_SLICES - 1).reduce((s, r) => s + Number(r[y] ?? 0), 0);
  return [...head, { [x]: "Other", [y]: other }];
}

export function ChartView({ spec, result }: { spec: ChartSpec; result: QueryResult }) {
  const [type, setType] = useState<ChartType>(spec.type);

  const data = useMemo(() => {
    const idx = Object.fromEntries(result.columns.map((c, i) => [c, i]));
    return result.rows.slice(0, spec.max_points).map((row) => {
      const point: Record<string, unknown> = { [spec.x]: row[idx[spec.x]] };
      for (const y of spec.y) point[y] = row[idx[y]];
      return point;
    });
  }, [result, spec]);

  const multi = spec.y.length > 1;
  const legend = multi ? <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, paddingTop: 8 }} /> : null;
  const grid = <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeWidth={1} />;
  const xAxis = <XAxis dataKey={spec.x} {...AXIS} interval="preserveStartEnd" minTickGap={16} />;
  const yAxis = <YAxis {...AXIS} axisLine={false} tickFormatter={formatCompact} width={56} />;
  const tooltip = <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--chart-grid)", opacity: 0.5 }} />;

  const chart = (() => {
    switch (type) {
      case "line":
        return (
          <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            {grid}{xAxis}{yAxis}{tooltip}{legend}
            {spec.y.map((y, i) => (
              <Line key={y} dataKey={y} type="monotone" stroke={SERIES[i]} strokeWidth={2} dot={false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--chart-surface)" }} />
            ))}
          </LineChart>
        );
      case "area":
        return (
          <AreaChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            {grid}{xAxis}{yAxis}{tooltip}{legend}
            {spec.y.map((y, i) => (
              <Area key={y} dataKey={y} type="monotone" stroke={SERIES[i]} strokeWidth={2} fill={SERIES[i]}
                fillOpacity={0.15} activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--chart-surface)" }} />
            ))}
          </AreaChart>
        );
      case "pie": {
        const y = spec.y[0];
        const slices = pieData(data, spec.x, y);
        return (
          <PieChart>
            <Tooltip content={<ChartTooltip />} />
            <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
            <Pie data={slices} dataKey={y} nameKey={spec.x} innerRadius="55%" outerRadius="85%"
              paddingAngle={1} stroke="var(--chart-surface)" strokeWidth={2}>
              {slices.map((_, i) => (
                <Cell key={i} fill={SERIES[i % SERIES.length]} />
              ))}
            </Pie>
          </PieChart>
        );
      }
      case "scatter":
        return (
          <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--chart-grid)" />
            <XAxis dataKey={spec.x} name={spec.x} type="number" {...AXIS} tickFormatter={formatCompact} />
            <YAxis dataKey={spec.y[0]} name={spec.y[0]} {...AXIS} axisLine={false} tickFormatter={formatCompact} width={56} />
            <Tooltip content={<ChartTooltip />} cursor={{ strokeDasharray: "0" }} />
            <Scatter data={data} fill={SERIES[0]} stroke="var(--chart-surface)" strokeWidth={2} />
          </ScatterChart>
        );
      default:
        return (
          <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }} barGap={2}>
            {grid}{xAxis}{yAxis}{tooltip}{legend}
            {spec.y.map((y, i) => (
              <Bar key={y} dataKey={y} fill={SERIES[i]} maxBarSize={24} radius={[4, 4, 0, 0]} />
            ))}
          </BarChart>
        );
    }
  })();

  const canSwitch = spec.type !== "scatter";

  return (
    <div className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="mb-3 flex items-center gap-3">
        <div className="min-w-0">
          <h4 className="truncate text-sm font-semibold">{spec.title || `${spec.y.join(", ")} by ${spec.x}`}</h4>
          {data.length < result.row_count && (
            <p className="text-xs text-zinc-500">Showing first {data.length} of {result.row_count} rows</p>
          )}
        </div>
        {canSwitch && (
          <div className="ml-auto flex shrink-0 rounded-lg border border-zinc-200 p-0.5 dark:border-zinc-800" role="group" aria-label="Chart type">
            {SWITCHABLE.filter((s) => s.type !== "pie" || !multi).map(({ type: t, icon: Icon, label }) => (
              <button
                key={t}
                onClick={() => setType(t)}
                aria-pressed={type === t}
                title={label}
                className={cn(
                  "rounded-md p-1.5 text-zinc-500 transition-colors hover:text-zinc-900 dark:hover:text-zinc-100",
                  type === t && "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100",
                )}
              >
                <Icon className="h-3.5 w-3.5" />
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {chart}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
