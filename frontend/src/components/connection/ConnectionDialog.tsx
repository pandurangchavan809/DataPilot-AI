import { AlertCircle, Database, Loader2, ShieldCheck, Sparkles } from "lucide-react";
import { type ChangeEvent, type FormEvent, type InputHTMLAttributes, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { useConnection } from "@/hooks/useConnection";
import { cn } from "@/utils";
import { useApp } from "@/hooks/useApp";
import type { DbType } from "@/types";

const TABS: { type: DbType; label: string; port?: number }[] = [
  { type: "sqlite_demo", label: "Demo" },
  { type: "postgresql", label: "PostgreSQL", port: 5432 },
  { type: "mysql", label: "MySQL", port: 3306 },
];

const EMPTY = { host: "", port: "", database: "", username: "", password: "", ssl: false };

export function ConnectionDialog() {
  const open = useApp((s) => s.connectOpen);
  const setOpen = useApp((s) => s.setConnectOpen);
  const allowed = useApp((s) => s.config?.db_types);
  const { connect, pending, error, setError } = useConnection();
  const tabs = TABS.filter((t) => !allowed || allowed.includes(t.type));
  const [type, setType] = useState<DbType>("sqlite_demo");
  const [form, setForm] = useState(EMPTY);

  useEffect(() => {
    if (open) setError(null);
  }, [open, setError]);

  const tab = tabs.find((t) => t.type === type) ?? tabs[0];
  const field = (key: keyof typeof EMPTY) => ({
    value: form[key] as string,
    onChange: (e: ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [key]: e.target.value })),
  });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const ok =
      type === "sqlite_demo"
        ? await connect({ type })
        : await connect({
            type,
            host: form.host.trim(),
            port: form.port ? Number(form.port) : tab?.port,
            database: form.database.trim(),
            username: form.username.trim(),
            password: form.password,
            ssl: form.ssl,
          });
    if (ok) {
      setForm((f) => ({ ...f, password: "" }));
      setOpen(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={() => setOpen(false)}
      title="Connect a database"
      description="DataPilot only ever runs read-only queries. Credentials live in your session and are never stored."
    >
      <div className="mb-5 flex rounded-xl bg-zinc-100 p-1 dark:bg-zinc-800/70" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.type}
            role="tab"
            aria-selected={type === t.type}
            onClick={() => (setType(t.type), setError(null))}
            className={cn(
              "flex-1 rounded-lg py-1.5 text-sm font-medium text-zinc-500 transition",
              type === t.type && "bg-white text-zinc-900 shadow-sm dark:bg-zinc-900 dark:text-zinc-100",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <form onSubmit={submit} className="space-y-4">
        {type === "sqlite_demo" ? (
          <div className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Sparkles className="h-4 w-4 text-brand-500" /> World Countries sample
            </div>
            <p className="mt-1.5 text-sm leading-6 text-zinc-500">
              50 countries across 5 related tables (economy, education, tourism and tech) on a bundled SQLite database. Perfect for a test drive.
            </p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-3">
              <Input label="Host" className="col-span-2" placeholder="db.example.com" required autoComplete="off" {...field("host")} />
              <Input label="Port" placeholder={String(tab?.port ?? "")} inputMode="numeric" pattern="[0-9]*" {...field("port")} />
            </div>
            <Input label="Database" placeholder="analytics" required autoComplete="off" {...field("database")} />
            <div className="grid grid-cols-2 gap-3">
              <Input label="Username" placeholder="readonly_user" required autoComplete="off" {...field("username")} />
              <Input label="Password" type="password" autoComplete="new-password" {...field("password")} />
            </div>
            <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
              <input
                type="checkbox"
                checked={form.ssl}
                onChange={(e) => setForm((f) => ({ ...f, ssl: e.target.checked }))}
                className="h-4 w-4 rounded accent-brand-600"
              />
              Require SSL/TLS (recommended for cloud databases)
            </label>
            <p className="flex items-start gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-xs leading-5 text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-300">
              <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Sessions are opened in read-only mode. For defence in depth, use a database user with SELECT-only privileges.
            </p>
          </>
        )}

        {error && (
          <p className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /> <span className="break-words">{error}</span>
          </p>
        )}

        <Button type="submit" variant="primary" className="w-full" disabled={pending}>
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Database className="h-4 w-4" />}
          {pending ? "Connecting…" : type === "sqlite_demo" ? "Load demo database" : "Test & connect"}
        </Button>
      </form>
    </Dialog>
  );
}

function Input({ label, className, ...props }: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className={cn("block", className)}>
      <span className="mb-1.5 block text-xs font-medium text-zinc-600 dark:text-zinc-400">{label}</span>
      <input
        {...props}
        className="h-10 w-full rounded-xl border border-zinc-200 bg-white px-3 text-sm outline-none transition placeholder:text-zinc-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/10 dark:border-zinc-700 dark:bg-zinc-950"
      />
    </label>
  );
}
