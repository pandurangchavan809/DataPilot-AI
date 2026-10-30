import { cn } from "@/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("h-7 w-7", className)} aria-hidden>
      <defs>
        <linearGradient id="dp-logo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6366f1" />
          <stop offset="1" stopColor="#06b6d4" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#dp-logo)" />
      <path
        d="M9 21.5V10.5h6.2c3.4 0 5.8 2.3 5.8 5.5s-2.4 5.5-5.8 5.5H9z"
        fill="none"
        stroke="#fff"
        strokeWidth="2.4"
        strokeLinejoin="round"
      />
      <circle cx="23.5" cy="10" r="2" fill="#fff" />
    </svg>
  );
}
