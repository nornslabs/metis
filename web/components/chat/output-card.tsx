import { ArrowRight, FileText, Gauge, Lightbulb, ListTree, Search, type LucideIcon } from "lucide-react";

import type { OutputPane } from "@/lib/workspace/panes";
import { cn } from "@/lib/utils";

const PANE_ICON: Readonly<Record<OutputPane, LucideIcon>> = {
  score: Gauge,
  research: Search,
  suggestions: Lightbulb,
  spec: FileText,
  plan: ListTree,
};

interface OutputCardProps {
  pane: OutputPane;
  title: string;
  /** One line under the title, e.g. "Promising · 55–74". */
  meta?: string;
  /** True while the output panel shows this pane: the card is outlined. */
  open: boolean;
  onOpen: (pane: OutputPane) => void;
}

/**
 * A one-line row in the chat that stands for an output: icon, title, meta, "Open →". It opens the
 * output panel on its pane; the report itself never renders in the chat (ui-context.md, OutputCard).
 */
export function OutputCard({ pane, title, meta, open, onOpen }: OutputCardProps) {
  const Icon = PANE_ICON[pane];
  return (
    <button
      type="button"
      aria-pressed={open}
      data-pane={pane}
      onClick={() => onOpen(pane)}
      className={cn(
        "flex w-full max-w-105 items-center gap-2.5 border px-2.5 py-1.5 text-left transition-colors hover:bg-accent",
        open && "border-foreground",
      )}
    >
      <span aria-hidden="true" className="grid size-7 shrink-0 place-items-center border text-muted-foreground">
        <Icon size={14} strokeWidth={2} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-control font-medium">{title}</span>
        {meta ? <span className="block truncate text-meta text-muted-foreground">{meta}</span> : null}
      </span>
      <span className="flex items-center gap-1 text-meta whitespace-nowrap text-muted-foreground">
        Open
        <ArrowRight size={12} strokeWidth={2} aria-hidden="true" />
      </span>
    </button>
  );
}
