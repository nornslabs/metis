"use client";

import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import type { ReactNode } from "react";

import { PaneBanner } from "@/components/panel/pane-banner";
import { PaneFooter } from "@/components/panel/pane-footer";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { countOf } from "@/lib/text/count";
import { PHASE_LIMITS } from "@/lib/schemas/plan";
import { blurOnEnterOrEscape, blurOnEscape } from "@/lib/plan/field-keys";
import type { DraftPhase, PhaseField } from "@/lib/plan/phases";
import { usePhaseReview, usePhaseReviewState } from "@/lib/plan/use-plan-state";

const FIELD_CLASS =
  "w-full min-w-0 resize-none border border-transparent bg-transparent px-1 py-0.5 text-control outline-none placeholder:text-muted-foreground hover:border-border focus:border-ring focus:bg-card disabled:hover:border-transparent";

interface PhaseCardProps {
  phase: DraftPhase;
  index: number;
  count: number;
  disabled: boolean;
  onEdit: (field: PhaseField, value: string) => void;
  onMove: (step: -1 | 1) => void;
  onRemove: () => void;
}

function IconButton({ label, disabled, onClick, children }: { label: string; disabled: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="grid size-6 place-items-center text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:bg-accent focus-visible:text-foreground focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
    >
      {children}
    </button>
  );
}

function PhaseCard({ phase, index, count, disabled, onEdit, onMove, onRemove }: PhaseCardProps) {
  const code = `P${index + 1}`;
  return (
    <li className="border bg-background">
      <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2 border-b py-1.5 pr-1.5 pl-2">
        <span className="border px-1 font-mono text-micro leading-4 text-muted-foreground">{code}</span>
        <input
          aria-label={`${code} name`}
          value={phase.name}
          disabled={disabled}
          maxLength={PHASE_LIMITS.name}
          placeholder="Phase name"
          className={cn(FIELD_CLASS, "font-semibold")}
          onChange={(event) => onEdit("name", event.target.value)}
          onKeyDown={blurOnEnterOrEscape}
        />
        <span className="flex">
          <IconButton label={`Move ${code} up`} disabled={disabled || index === 0} onClick={() => onMove(-1)}>
            <ArrowUp size={13} strokeWidth={2} aria-hidden="true" />
          </IconButton>
          <IconButton label={`Move ${code} down`} disabled={disabled || index === count - 1} onClick={() => onMove(1)}>
            <ArrowDown size={13} strokeWidth={2} aria-hidden="true" />
          </IconButton>
          <IconButton label={`Delete ${code}`} disabled={disabled || count < 2} onClick={onRemove}>
            <Trash2 size={13} strokeWidth={2} aria-hidden="true" />
          </IconButton>
        </span>
      </div>
      {(
        [
          ["goal", "Goal", "What this phase delivers"],
          ["exit_criteria", "Done when", "Exit criteria"],
        ] as const
      ).map(([field, label, placeholder]) => (
        <label key={field} className="grid grid-cols-[auto_1fr] gap-2 px-2 py-1.5 text-control not-first:pt-0">
          <span className="w-18 pt-1 text-meta text-muted-foreground">{label}</span>
          <textarea
            aria-label={`${code} ${label}`}
            value={phase[field]}
            rows={1}
            disabled={disabled}
            maxLength={PHASE_LIMITS.text}
            placeholder={placeholder}
            className={cn(FIELD_CLASS, "field-sizing-content")}
            onChange={(event) => onEdit(field, event.target.value)}
            onKeyDown={blurOnEscape}
          />
        </label>
      ))}
    </li>
  );
}

/** The phase review: one card per proposed phase, editable until the phases are approved. */
export function PhaseReviewBody({ ideaId }: { ideaId: string }) {
  const review = usePhaseReview(ideaId);
  const state = usePhaseReviewState(review);
  if (state.status === "sent") {
    return (
      <p role="status" className="px-4 py-3.5 text-control text-muted-foreground">
        Planning tasks…
      </p>
    );
  }
  const disabled = state.status === "sending";
  return (
    <div className="px-4 py-3.5">
      <p className="mb-2.5 text-meta text-muted-foreground">Rename, reorder or add phases. Metis writes tasks after you approve.</p>
      {state.status === "failed" ? (
        <PaneBanner className="mb-3">
          <span>
            <b className="font-medium">Could not send the phases.</b> {state.error} Your edits are kept.
          </span>
        </PaneBanner>
      ) : null}
      <ol className="grid gap-2">
        {state.phases.map((phase, index) => (
          <PhaseCard
            key={phase.key}
            phase={phase}
            index={index}
            count={state.phases.length}
            disabled={disabled}
            onEdit={(field, value) => review.edit(phase.key, field, value)}
            onMove={(step) => review.move(phase.key, step)}
            onRemove={() => review.remove(phase.key)}
          />
        ))}
      </ol>
      <button
        type="button"
        disabled={disabled || state.phases.length >= PHASE_LIMITS.maxPhases}
        onClick={() => review.add()}
        className="mt-2 flex w-full items-center justify-center gap-1.5 border p-2 text-control text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:bg-accent focus-visible:text-foreground focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Plus size={13} strokeWidth={2} aria-hidden="true" />
        Add phase
      </button>
    </div>
  );
}

/** The review's footer: "n phases · edited" and Approve phases. */
export function PhaseReviewFooter({ ideaId }: { ideaId: string }) {
  const review = usePhaseReview(ideaId);
  const state = usePhaseReviewState(review);
  const blocked = review.blockedReason();
  const edited = review.edited();
  const sent = state.status === "sent";
  return (
    <PaneFooter
      meta={
        <span role="status" aria-live="polite">
          {sent ? "Approved" : `${countOf(state.phases.length, "phase")}${edited ? " · edited" : ""}`}
        </span>
      }
    >
      {sent ? null : (
        <Button type="button" size="sm" disabled={blocked !== null} title={blocked ?? undefined} onClick={() => void review.approve()}>
          Approve phases
        </Button>
      )}
    </PaneFooter>
  );
}
