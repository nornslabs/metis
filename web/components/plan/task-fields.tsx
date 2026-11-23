"use client";

import { useState, type ReactNode } from "react";

import { cn } from "@/lib/cn";
import type { PlanEditor } from "@/lib/plan/plan-editor";
import type { PlanView, TaskView } from "@/lib/plan/view";
import { ESTIMATES, taskTitleSchema } from "@/lib/schemas/plan";

const INPUT_CLASS =
  "h-7 w-full min-w-0 border bg-background px-2 text-control text-foreground outline-none focus:border-ring focus:ring-3 focus:ring-ring/20 disabled:opacity-60";

/** A labelled row of the task details: label left, control right. */
export function DetailField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[auto_1fr] items-center gap-2">
      <span className="w-18 text-meta text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

interface FieldProps {
  view: TaskView;
  editor: PlanEditor;
}

/** The title input: saved on blur or Enter, validated 1–200, Esc puts the saved title back. */
export function TitleField({ view, editor }: FieldProps) {
  const [value, setValue] = useState(view.task.title);
  const [problem, setProblem] = useState<string | null>(null);
  const commit = () => {
    const parsed = taskTitleSchema.safeParse(value);
    if (!parsed.success) {
      setProblem(parsed.error.issues[0]?.message ?? "Check the title.");
      return;
    }
    setProblem(null);
    if (parsed.data !== view.task.title) editor.edit(view.task.id, { title: parsed.data });
  };
  return (
    <div className="grid gap-1">
      <input
        aria-label={`${view.code} title`}
        aria-invalid={problem !== null}
        value={value}
        className={INPUT_CLASS}
        onChange={(event) => setValue(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
          if (event.key !== "Escape") return;
          setValue(view.task.title);
          setProblem(null);
          event.currentTarget.blur();
        }}
      />
      {problem ? (
        <span role="alert" className="text-meta text-destructive">
          {problem}
        </span>
      ) : null}
    </div>
  );
}

/** The estimate as a radio group of 1 2 3 5 8. */
export function EstimateSegment({ view, editor }: FieldProps) {
  return (
    <div role="radiogroup" aria-label={`${view.code} estimate`} className="inline-grid w-max grid-cols-5 border">
      {ESTIMATES.map((estimate) => (
        <button
          key={estimate}
          type="button"
          role="radio"
          aria-checked={view.task.estimate === estimate}
          onClick={() => {
            if (estimate !== view.task.estimate) editor.edit(view.task.id, { estimate });
          }}
          className={cn(
            "h-6 w-7 font-mono text-meta text-muted-foreground not-first:border-l focus-visible:bg-accent focus-visible:outline-none",
            view.task.estimate === estimate ? "bg-foreground text-background focus-visible:bg-foreground" : "hover:bg-accent hover:text-foreground",
          )}
        >
          {estimate}
        </button>
      ))}
    </div>
  );
}

/** The phase a task sits in; changing it moves the task to the end of that phase. */
export function PhaseSelect({ view, plan, editor }: FieldProps & { plan: PlanView }) {
  return (
    <select
      aria-label={`${view.code} phase`}
      value={plan.phases[view.phaseIndex]?.phase.id ?? ""}
      className={INPUT_CLASS}
      onChange={(event) => editor.edit(view.task.id, { phase_id: event.target.value })}
    >
      {plan.phases.map((phase) => (
        <option key={phase.phase.id} value={phase.phase.id}>
          {`${phase.code} · ${phase.phase.name || "Untitled"}`}
        </option>
      ))}
    </select>
  );
}
