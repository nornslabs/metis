import { cn } from "@/lib/cn";
import type { IdeaFilter } from "@/lib/api/queries/use-ideas";

const FILTERS: readonly { value: IdeaFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "in_progress", label: "In progress" },
  { value: "scored", label: "Scored" },
];

/** The All / In progress / Scored segment. */
export function HistoryFilters({ value, onChange }: { value: IdeaFilter; onChange: (next: IdeaFilter) => void }) {
  return (
    <div role="group" aria-label="Filter" className="flex shrink-0 border-b">
      {FILTERS.map((filter) => (
        <button
          key={filter.value}
          type="button"
          aria-pressed={value === filter.value}
          onClick={() => onChange(filter.value)}
          className={cn(
            "flex-1 py-1.5 text-note text-muted-foreground outline-none focus-visible:bg-accent",
            "not-first:border-l aria-pressed:bg-accent aria-pressed:text-foreground",
          )}
        >
          {filter.label}
        </button>
      ))}
    </div>
  );
}
