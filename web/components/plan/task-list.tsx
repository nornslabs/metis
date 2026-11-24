"use client";

import { useEffect } from "react";

import { TaskRow } from "@/components/plan/task-row";
import type { PlanEditor } from "@/lib/plan/plan-editor";
import type { PlanView } from "@/lib/plan/view";
import { useReducedMotion } from "@/lib/use-reduced-motion";

/** A request to land on a task. `nonce` makes a second request for the same task a new one. */
export interface TaskTarget {
  readonly id: string;
  readonly nonce: number;
}

const FLASH_MS = 1600;

/** Scrolls the task into view and flashes its row (the `data-flash` animation restarts each time). */
function useFlash(target: TaskTarget | null, reduced: boolean): void {
  useEffect(() => {
    if (target === null) return;
    const row = document.getElementById(`plan-task-${target.id}`);
    if (!row) return;
    row.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" });
    delete row.dataset.flash;
    void row.offsetWidth;
    row.dataset.flash = "";
    const timer = window.setTimeout(() => delete row.dataset.flash, FLASH_MS);
    return () => window.clearTimeout(timer);
  }, [target, reduced]);
}

interface TaskListProps {
  plan: PlanView;
  open: ReadonlySet<string>;
  target: TaskTarget | null;
  locked: boolean;
  editor: PlanEditor;
  onToggle: (taskId: string) => void;
  onGo: (taskId: string) => void;
}

/** The plan as phases (code, name, points) with a row per task. */
export function TaskList({ plan, open, target, locked, editor, onToggle, onGo }: TaskListProps) {
  const reduced = useReducedMotion();
  useFlash(target, reduced);
  return (
    <div>
      {plan.phases.map((phase) => (
        <section key={phase.phase.id} aria-label={`${phase.code} ${phase.phase.name}`} className="border-b">
          <h4 className="flex items-center gap-2 px-4 pt-2.5 pb-1.5 text-control">
            <span className="border px-1 font-mono text-micro leading-4 text-muted-foreground">{phase.code}</span>
            <b className="min-w-0 truncate font-semibold">{phase.phase.name || "Untitled phase"}</b>
            <span className="ml-auto font-mono text-meta text-muted-foreground">{`${phase.points} pts`}</span>
          </h4>
          {phase.tasks.length > 0 ? (
            <ul>
              {phase.tasks.map((view) => (
                <TaskRow
                  key={view.task.id}
                  view={view}
                  plan={plan}
                  open={open.has(view.task.id)}
                  locked={locked}
                  editor={editor}
                  onToggle={() => onToggle(view.task.id)}
                  onGo={onGo}
                />
              ))}
            </ul>
          ) : (
            <p className="px-4 pt-0.5 pb-3 text-control text-muted-foreground">No tasks in this phase yet.</p>
          )}
        </section>
      ))}
    </div>
  );
}
