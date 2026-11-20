"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { BandBadge } from "@/components/score/band-badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import type { AdviceInterrupt } from "@/lib/events/schemas";
import { DECISION_LABELS, buildResume, reviseSchema, type AdviceDecision as DecisionKind, type AdviceResume, type ReviseFormValues } from "@/lib/scores/decision";
import { MAX_TOTAL, type Suggestion } from "@/lib/scores/view";

interface AdviceDecisionProps {
  interrupt: AdviceInterrupt;
  /** The idea's text, which the revise editor starts from. */
  ideaText: string;
  /** The accepted suggestions of the advised score run: a revision adds them to the idea. */
  accepted: readonly Suggestion[];
  disabled: boolean;
  onDecide: (value: AdviceResume, decision: DecisionKind) => void;
}

/** The run paused on a low score: revise and rescore, continue to the spec anyway, or stop here. */
export function AdviceDecision({ interrupt, ideaText, accepted, disabled, onDecide }: AdviceDecisionProps) {
  const [revising, setRevising] = useState(false);
  const form = useForm<ReviseFormValues>({ resolver: zodResolver(reviseSchema), defaultValues: { text: ideaText } });
  const send = form.handleSubmit(({ text }) => onDecide(buildResume("revise", text, accepted), "revise"));

  return (
    <div role="group" aria-label="Decide what happens next" className="flex flex-col gap-2 border px-2.5 py-2">
      <p className="flex flex-wrap items-center gap-2 text-body">
        <span className="font-medium tabular-nums">
          {interrupt.total} / {MAX_TOTAL}
        </span>
        <BandBadge band={interrupt.band} />
      </p>
      <p className="text-control text-muted-foreground">This idea scored below the build line. What next?</p>
      <div className="flex flex-wrap gap-1.5">
        <Button type="button" size="sm" disabled={disabled} aria-expanded={revising} onClick={() => setRevising((current) => !current)}>
          Revise idea and rescore
        </Button>
        <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => onDecide(buildResume("continue"), "continue")}>
          {`${DECISION_LABELS.continue} anyway`}
        </Button>
        <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => onDecide(buildResume("stop"), "stop")}>
          {DECISION_LABELS.stop}
        </Button>
      </div>
      {revising ? (
        <form onSubmit={send} className="flex flex-col gap-1.5" noValidate>
          <Label htmlFor="advice-revised-text" className="text-meta font-medium text-muted-foreground uppercase tracking-label">
            Revised idea
          </Label>
          <textarea
            id="advice-revised-text"
            rows={6}
            disabled={disabled}
            aria-invalid={form.formState.errors.text ? true : undefined}
            className="w-full resize-y border bg-transparent px-2 py-1.5 text-control"
            {...form.register("text")}
          />
          {form.formState.errors.text ? (
            <p role="alert" className="text-meta text-destructive">
              {form.formState.errors.text.message}
            </p>
          ) : null}
          {accepted.length > 0 ? (
            <div className="flex flex-col gap-0.5">
              <p className="text-meta text-muted-foreground">Accepted suggestions added to the idea:</p>
              <ul className="list-disc pl-4 text-control">
                {accepted.map((suggestion) => (
                  <li key={suggestion.id} className="break-words">
                    {suggestion.title}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-meta text-muted-foreground">Accept suggestions above to add them to the idea.</p>
          )}
          <div>
            <Button type="submit" size="sm" disabled={disabled}>
              Send revision
            </Button>
          </div>
        </form>
      ) : null}
    </div>
  );
}
