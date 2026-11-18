import { Check } from "lucide-react";

import type { RunStep } from "@/lib/events/reducer";
import { nodeLabel } from "@/lib/events/labels";
import { cn } from "@/lib/utils";

interface StepListProps {
  steps: readonly RunStep[];
  /** False once the run ended: a step still open then shows no spinner. */
  live: boolean;
}

function StepIcon({ done, live }: { done: boolean; live: boolean }) {
  if (done) return <Check size={12} strokeWidth={2.5} aria-hidden="true" />;
  if (!live) return <span aria-hidden="true" className="size-2 border" />;
  return (
    <span
      aria-hidden="true"
      className="size-3 animate-spin border-2 border-border border-t-current motion-reduce:animate-none"
    />
  );
}

/** One row per specialist step: spinner while it runs, check when done (ui-context.md, StepList). */
export function StepList({ steps, live }: StepListProps) {
  if (steps.length === 0) return null;
  return (
    <ol aria-label="Steps" className="flex flex-col gap-0.5 border px-2.5 py-1.5 text-xs">
      {steps.map((step, index) => (
        <li
          key={`${step.node}-${index}`}
          data-done={step.done}
          className={cn("flex flex-col", step.done ? "text-foreground" : "text-muted-foreground")}
        >
          <span className="flex items-center gap-1.5">
            <span className="grid size-3.5 place-items-center">
              <StepIcon done={step.done} live={live} />
            </span>
            {nodeLabel(step.node)}
            <span className="sr-only">{step.done ? "(done)" : "(running)"}</span>
          </span>
          {step.tools.length > 0 ? (
            <span className="pl-5 font-mono text-meta text-muted-foreground">{step.tools.join(" · ")}</span>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
