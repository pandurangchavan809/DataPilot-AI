import { Eye, EyeOff, KeyRound, Loader2 } from "lucide-react";
import { type FormEvent, useState } from "react";

import { ApiError } from "@/api";
import { Button } from "@/components/ui/Button";
import { Logo } from "@/components/ui/Logo";
import { DEMO_ACCOUNT, useAuth } from "@/hooks/useAuth";
import { cn } from "@/utils";

type Mode = "login" | "signup";

const inputClass =
  "h-10 w-full rounded-xl border border-zinc-200 bg-white px-3 text-sm outline-none transition-colors placeholder:text-zinc-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 dark:border-zinc-800 dark:bg-zinc-900";

export function AuthPage() {
  const login = useAuth((s) => s.login);
  const signup = useAuth((s) => s.signup);
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  const switchMode = (next: Mode) => {
    setMode(next);
    setError("");
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setPending(true);
    setError("");
    try {
      await (mode === "login" ? login : signup)(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setPending(false);
    }
  };

  const fillDemo = () => {
    switchMode("login");
    setEmail(DEMO_ACCOUNT.email);
    setPassword(DEMO_ACCOUNT.password);
  };

  return (
    <div className="flex min-h-full items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm animate-fade-in">
        <div className="flex flex-col items-center text-center">
          <Logo className="h-10 w-10" />
          <h1 className="mt-4 text-xl font-semibold tracking-tight">
            {mode === "login" ? "Log in to DataPilot" : "Create your account"}
          </h1>
          <p className="mt-1 text-sm text-zinc-500">Ask your database questions in plain English.</p>
        </div>

        <div className="mt-6 grid grid-cols-2 rounded-xl bg-zinc-100 p-1 text-sm dark:bg-zinc-900">
          {(["login", "signup"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => switchMode(m)}
              className={cn(
                "h-8 rounded-lg font-medium transition-colors",
                mode === m
                  ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-800 dark:text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200",
              )}
            >
              {m === "login" ? "Log in" : "Sign up"}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="mt-5 space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">Email</span>
            <input
              className={inputClass}
              type={mode === "signup" ? "email" : "text"}
              autoComplete={mode === "login" ? "username" : "email"}
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">Password</span>
            <div className="relative">
              <input
                className={cn(inputClass, "pr-10")}
                type={showPassword ? "text" : "password"}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                placeholder={mode === "signup" ? "At least 8 characters, a letter and a number" : "Your password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </label>

          {error && (
            <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-500/10 dark:text-red-400">
              {error}
            </p>
          )}

          <Button type="submit" variant="primary" className="w-full" disabled={pending}>
            {pending && <Loader2 className="h-4 w-4 animate-spin" />}
            {mode === "login" ? "Log in" : "Create account"}
          </Button>
        </form>

        <div className="mt-6 rounded-xl border border-dashed border-zinc-300 p-4 dark:border-zinc-700">
          <div className="flex items-center gap-2 text-sm font-medium">
            <KeyRound className="h-4 w-4 text-brand-500" /> Demo account
          </div>
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
            <dt className="text-zinc-500">Email</dt>
            <dd className="font-mono">{DEMO_ACCOUNT.email}</dd>
            <dt className="text-zinc-500">Password</dt>
            <dd className="font-mono">{DEMO_ACCOUNT.password}</dd>
          </dl>
          <Button variant="secondary" size="sm" className="mt-3 w-full" onClick={fillDemo}>
            Use demo account
          </Button>
        </div>
      </div>
    </div>
  );
}
