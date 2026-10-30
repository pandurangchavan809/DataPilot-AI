import clsx, { type ClassValue } from "clsx";

export const cn = (...inputs: ClassValue[]) => clsx(inputs);

/** "pandurang809@gmail.com" -> "pandurang809" */
export const displayName = (email: string) => email.split("@")[0];

/** "pandurang809@gmail.com" -> "PA" */
export const initials = (email: string) => displayName(email).slice(0, 2).toUpperCase();

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 });
const full = new Intl.NumberFormat("en", { maximumFractionDigits: 2 });

export function formatCompact(value: unknown): string {
  return typeof value === "number" ? compact.format(value) : String(value ?? "");
}

export function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "number") return Math.abs(value) >= 1e15 ? compact.format(value) : full.format(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

export function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function toCsv(columns: string[], rows: unknown[][]): string {
  const escape = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [columns.map(escape).join(","), ...rows.map((r) => r.map(escape).join(","))].join("\r\n");
}

export function downloadText(filename: string, text: string, mime = "text/csv;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

export function uid(): string {
  return crypto.randomUUID();
}
