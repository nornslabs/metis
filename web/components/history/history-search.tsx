import { Search } from "lucide-react";
import type { RefObject } from "react";

interface HistorySearchProps {
  value: string;
  onChange: (next: string) => void;
  inputRef: RefObject<HTMLInputElement | null>;
}

/** The search box; `/` focuses it from anywhere on the page (handled by the panels provider). */
export function HistorySearch({ value, onChange, inputRef }: HistorySearchProps) {
  return (
    <label className="flex h-9 shrink-0 items-center gap-2 border-b px-3 text-muted-foreground">
      <Search size={14} strokeWidth={2} aria-hidden="true" />
      <input
        ref={inputRef}
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search ideas"
        aria-label="Search ideas"
        maxLength={100}
        className="min-w-0 flex-1 bg-transparent text-control text-foreground outline-none placeholder:text-muted-foreground"
      />
      <kbd className="border px-1 font-mono text-meta leading-4" aria-hidden="true">
        /
      </kbd>
    </label>
  );
}
