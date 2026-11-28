import { Check, Minus } from "lucide-react";

import type { RunStep } from "@/lib/events/reducer";
import { gateItemLabel, nodeLabel, toolLabel } from "@/lib/events/labels";
import { cn } from "@/lib/utils";

interface StepListProps {
  steps: readonly RunStep[];
  /** False once the run ended: a step still open then shows no spinner. */
  live: boolean;
}

function StepIcon({ done, skipped, live }: { done: boolean; skipped: boolean; live: boolean }) {
  if (skipped) return <Minus size={12} strokeWidth={2.5} aria-hidden="true" />;
  if (done) return <Check size={12} strokeWidth={2.5} aria-hidden="true" />;
  if (!live) return <span aria-hidden="true" className="size-2 border" />;
  return (
    <span
      aria-hidden="true"
      className="size-3 animate-spin rounded-full border-2 border-border border-t-current motion-reduce:animate-none"
    />
  );
}

/** Screen-reader state of a step; a skipped step already says "(skipped)" in text. */
function stepStateLabel(step: RunStep): string {
  if (step.skipped) return "";
  return step.done ? "(done)" : "(running)";
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
          data-skipped={step.skipped === true}
          className={cn("flex flex-col", step.done && !step.skipped ? "text-foreground" : "text-muted-foreground")}
        >
          <span className="flex items-center gap-1.5">
            <span className="grid size-3.5 place-items-center">
              <StepIcon done={step.done} skipped={step.skipped === true} live={live} />
            </span>
            {nodeLabel(step.node)}
            {step.skipped ? <span className="text-muted-foreground">(skipped)</span> : null}
            <span className="sr-only">{stepStateLabel(step)}</span>
          </span>
          {step.tools.length > 0 ? (
            <span className="pl-5 font-mono text-meta text-muted-foreground">
              {step.tools.map(toolLabel).join(" · ")}
            </span>
          ) : null}
          {(step.skips ?? []).map((skip, skipIndex) => (
            <span
              key={`${skip.gate}-${skipIndex}`}
              data-testid="gate-skip"
              className="pl-5 text-meta text-muted-foreground"
            >
              {nodeLabel(step.node)} skipped {gateItemLabel(skip.gate)}: {skip.reason}
            </span>
          ))}
        </li>
      ))}
    </ol>
  );
}
