"use client";

import { useTheme } from "next-themes";

import { cn } from "@/lib/utils";

const THEMES = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
] as const;

/** Light / dark / system as a bordered three-way segment. */
export function ThemeSegment({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  return (
    <div role="group" aria-label="Theme" className={cn("grid grid-cols-3 border", className)}>
      {THEMES.map(({ value, label }) => (
        <button
          key={value}
          type="button"
          aria-pressed={theme === value}
          onClick={() => setTheme(value)}
          className={cn(
            "py-1 text-meta text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring",
            "not-first:border-l aria-pressed:bg-foreground aria-pressed:text-background",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
