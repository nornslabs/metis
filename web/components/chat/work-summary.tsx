"use client";

import { ChevronRight } from "lucide-react";
import { useId, useState } from "react";

import { StepList } from "@/components/chat/step-list";
import type { RunStep } from "@/lib/events/reducer";
import { workSummaryLine } from "@/lib/events/work-summary";
import { cn } from "@/lib/utils";

interface WorkSummaryProps {
  steps: readonly RunStep[];
  /** Sources the Researcher used, when known: "Researched 6 sources". */
  sourceCount: number | null;
  /** True while the run works: the steps show in the dock's working bar, not here. */
  working: boolean;
}

/** The chat's one line for finished work; it expands to the step list (ui-context.md, WorkSummary). */
export function WorkSummary({ steps, sourceCount, working }: WorkSummaryProps) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const line = workSummaryLine(steps, sourceCount);
  if (working || line === null) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((current) => !current)}
        className="flex w-max items-center gap-1.5 py-0.5 text-note text-muted-foreground hover:text-foreground"
      >
        <ChevronRight
          size={12}
          strokeWidth={2}
          aria-hidden="true"
          className={cn("transition-transform motion-reduce:transition-none", open && "rotate-90")}
        />
        {line}
      </button>
      <div id={listId} hidden={!open}>
        <StepList steps={steps} live={false} />
      </div>
    </div>
  );
}
