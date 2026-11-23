"use client";

import { Button } from "@/components/ui/button";
import type { PhaseReviewInterrupt } from "@/lib/events/schemas";
import { countOf } from "@/lib/text/count";
import { usePhaseReview, usePhaseReviewState } from "@/lib/plan/use-plan-state";

interface PhaseReviewPromptProps {
  ideaId: string;
  interrupt: PhaseReviewInterrupt;
  onOpenPhases: () => void;
}

/** The run waits for the phases: approve them here (same as the pane's footer) or open the pane to edit them. */
export function PhaseReviewPrompt({ ideaId, interrupt, onOpenPhases }: PhaseReviewPromptProps) {
  const review = usePhaseReview(ideaId);
  const state = usePhaseReviewState(review);
  const blocked = review.blockedReason();
  if (state.status === "sent") {
    return (
      <p role="status" className="border px-2.5 py-2 text-control text-muted-foreground">
        Phases approved. Planning tasks…
      </p>
    );
  }
  const count = state.phases.length > 0 ? state.phases.length : interrupt.phases.length;
  return (
    <div role="group" aria-label="Review the phases" className="flex flex-col gap-2 border px-2.5 py-2">
      <p className="text-control text-muted-foreground">{`${countOf(count, "phase")} proposed. Review them, then approve to plan the tasks.`}</p>
      {state.status === "failed" && state.error ? (
        <p role="alert" className="text-meta text-destructive">
          {state.error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-1.5">
        <Button type="button" size="sm" disabled={blocked !== null} title={blocked ?? undefined} onClick={() => void review.approve()}>
          Approve phases
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onOpenPhases}>
          Open the phases
        </Button>
      </div>
    </div>
  );
}
