"use client";

import { ChevronRight } from "lucide-react";

import { DetailField, EstimateSegment, PhaseSelect, TitleField } from "@/components/plan/task-fields";
import { cn } from "@/lib/cn";
import type { PlanEditor } from "@/lib/plan/plan-editor";
import { blockersOf, type PlanView, type TaskView } from "@/lib/plan/view";

const MONO_BOX = "border font-mono leading-4 text-muted-foreground";

/** A `← T4` chip: jumps to the task that blocks this one. */
function BlockerChip({ code, title, onGo, compact }: { code: string; title: string; onGo: () => void; compact: boolean }) {
  return (
    <button
      type="button"
      aria-label={`Blocked by ${code}: ${title}`}
      onClick={(event) => {
        event.stopPropagation();
        onGo();
      }}
      className={cn(
        MONO_BOX,
        "cursor-pointer px-1 text-micro whitespace-nowrap hover:border-ring hover:text-foreground focus-visible:border-ring focus-visible:text-foreground focus-visible:outline-none",
      )}
    >
      {compact ? `← ${code}` : `${code} · ${title}`}
    </button>
  );
}

interface TaskDetailsProps {
  view: TaskView;
  plan: PlanView;
  locked: boolean;
  editor: PlanEditor;
  onGo: (taskId: string) => void;
}

function TaskDetails({ view, plan, locked, editor, onGo }: TaskDetailsProps) {
  const { task } = view;
  const blockers = blockersOf(plan, task);
  return (
    <div className="grid gap-2 bg-background px-4 pt-2 pb-3 pl-13.5 text-control max-narrow:pl-4">
      <p className="m-0 break-words whitespace-pre-wrap text-muted-foreground">{task.description || "No description."}</p>
      {locked ? null : (
        <>
          <DetailField label="Title">
            <TitleField key={`${task.id}:${task.title}`} view={view} editor={editor} />
          </DetailField>
          <DetailField label="Estimate">
            <EstimateSegment view={view} editor={editor} />
          </DetailField>
          <DetailField label="Phase">
            <PhaseSelect view={view} plan={plan} editor={editor} />
          </DetailField>
        </>
      )}
      <DetailField label="Labels">
        {task.labels.length > 0 ? (
          <span className="flex flex-wrap gap-1">
            {task.labels.map((label) => (
              <span key={label} className="border px-1 text-micro leading-4 text-muted-foreground">
                {label}
              </span>
            ))}
          </span>
        ) : (
          <span className="text-muted-foreground">None</span>
        )}
      </DetailField>
      <DetailField label="Blocked by">
        {blockers.length > 0 ? (
          <span className="flex flex-wrap gap-1">
            {blockers.map((blocker) => (
              <BlockerChip key={blocker.task.id} code={blocker.code} title={blocker.task.title} compact={false} onGo={() => onGo(blocker.task.id)} />
            ))}
          </span>
        ) : (
          <span className="text-muted-foreground">Nothing</span>
        )}
      </DetailField>
    </div>
  );
}

interface TaskRowProps {
  view: TaskView;
  plan: PlanView;
  open: boolean;
  locked: boolean;
  editor: PlanEditor;
  onToggle: () => void;
  onGo: (taskId: string) => void;
}

/** One task: the row (id, title, blockers, estimate) and, when open, its details and edit fields. */
export function TaskRow({ view, plan, open, locked, editor, onToggle, onGo }: TaskRowProps) {
  const { task } = view;
  const blockers = blockersOf(plan, task);
  return (
    <li
      id={`plan-task-${task.id}`}
      data-critical={view.critical ? "" : undefined}
      className={cn("relative data-flash:animate-src-flash motion-reduce:animate-none", view.critical && "before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-foreground")}
    >
      <div
        className={cn(
          "grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-2 border-t px-4 py-1.5 text-control hover:bg-accent focus-within:bg-accent",
          open && "bg-accent",
        )}
      >
        <button
          type="button"
          aria-expanded={open}
          aria-label={`${view.code}: ${task.title}, ${task.estimate} points`}
          onClick={onToggle}
          className="col-span-2 grid grid-cols-subgrid items-center gap-2 text-left outline-none"
        >
          <span className="w-7 font-mono text-micro text-muted-foreground">{view.code}</span>
          <span className="truncate">{task.title}</span>
        </button>
        <span className="flex gap-1 max-narrow:hidden">
          {blockers.map((blocker) => (
            <BlockerChip key={blocker.task.id} code={blocker.code} title={blocker.task.title} compact onGo={() => onGo(blocker.task.id)} />
          ))}
        </span>
        <span className={cn(MONO_BOX, "min-w-5.5 text-center text-meta")}>{task.estimate}</span>
        <ChevronRight size={12} aria-hidden="true" className={cn("text-muted-foreground transition-transform", open && "rotate-90")} />
      </div>
      {open ? <TaskDetails view={view} plan={plan} locked={locked} editor={editor} onGo={onGo} /> : null}
    </li>
  );
}
