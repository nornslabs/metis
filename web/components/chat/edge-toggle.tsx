"use client";

import { PanelLeft, PanelRight } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useOutputAvailability } from "@/lib/workspace/output-availability";
import { useWorkspacePanels } from "@/lib/workspace/workspace-panels";
import { cn } from "@/lib/utils";

export type EdgeToggleSide = "left" | "right";

const TOGGLE_CLASS = cn(
  "absolute top-3 z-20 grid size-7 place-items-center border bg-background text-muted-foreground",
  "transition-colors hover:border-ring hover:text-foreground aria-pressed:bg-accent aria-pressed:text-foreground",
  "aria-disabled:cursor-not-allowed aria-disabled:opacity-35 aria-disabled:hover:border-border aria-disabled:hover:text-muted-foreground",
  // Hidden (not focusable) while its own panel is open; back at once when it closes.
  "data-[hidden=true]:invisible data-[hidden=true]:opacity-0 data-[hidden=true]:transition-[opacity,visibility] data-[hidden=true]:delay-0 data-[hidden=true]:duration-150",
  "max-guides:top-2",
);

const SIDE_CLASS: Record<EdgeToggleSide, string> = {
  // The probe this sits in is the chat column, so its edges are the guide lines: centre on them.
  left: "left-0 -translate-x-1/2 max-guides:translate-x-0 max-guides:left-2",
  right: "right-0 translate-x-1/2 max-guides:translate-x-0 max-guides:right-2",
};

/**
 * A 28px square on one of the chat column's guide lines. Left opens the history panel, right the
 * output panel (disabled until an output exists, dotted while one is unseen). Place it inside the
 * column probe (`ColumnProbe`) so it follows the column while panels move it.
 */
export function EdgeToggle({ side }: { side: EdgeToggleSide }) {
  const panels = useWorkspacePanels();
  const availability = useOutputAvailability();

  const isLeft = side === "left";
  const open = isLeft ? panels.historyOpen : panels.outputOpen;
  const hasOutput = availability.panes.length > 0;
  const disabled = !isLeft && !hasOutput;
  const label = isLeft ? "Your ideas" : "Outputs";
  const Icon = isLeft ? PanelLeft : PanelRight;

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            ref={panels.toggleRefs[isLeft ? "history" : "output"]}
            type="button"
            aria-label={label}
            aria-controls={isLeft ? "history-panel" : "output-panel"}
            aria-expanded={open}
            aria-pressed={open}
            aria-disabled={disabled || undefined}
            data-hidden={open}
            tabIndex={open ? -1 : undefined}
            onClick={() => {
              if (disabled) return;
              if (isLeft) panels.openHistory();
              else panels.openOutput();
            }}
            className={cn(TOGGLE_CLASS, SIDE_CLASS[side])}
          />
        }
      >
        <Icon size={14} strokeWidth={2} />
        {!isLeft && availability.unseen && hasOutput ? (
          <span
            data-testid="output-unseen-dot"
            aria-hidden="true"
            className="absolute -top-0.75 -right-0.75 size-1.5 border border-background bg-foreground"
          />
        ) : null}
      </TooltipTrigger>
      <TooltipContent side="bottom">{isLeft ? "Your ideas (/)" : label}</TooltipContent>
    </Tooltip>
  );
}
