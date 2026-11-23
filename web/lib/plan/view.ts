import type { Plan, PlanPhase, PlanTask } from "@/lib/schemas/plan";

/** A task with the labels the pane shows: its number in plan order (T1…) and its phase (P1…). */
export interface TaskView {
  readonly task: PlanTask;
  /** `T7`: the task's place in plan order (phase, then position). One scheme in list, chips and graph. */
  readonly code: string;
  readonly phaseIndex: number;
  readonly phaseCode: string;
  readonly critical: boolean;
}

export interface PhaseView {
  readonly phase: PlanPhase;
  readonly code: string;
  readonly points: number;
  readonly tasks: readonly TaskView[];
}

export interface PlanSummary {
  readonly phases: number;
  readonly tasks: number;
  readonly points: number;
  readonly criticalPoints: number;
  readonly criticalTasks: number;
}

export interface PlanView {
  readonly phases: readonly PhaseView[];
  readonly tasks: readonly TaskView[];
  readonly byId: ReadonlyMap<string, TaskView>;
  readonly summary: PlanSummary;
}

/** The tasks that block `task`, in the order the server lists them (a blocker outside the plan is skipped). */
export function blockersOf(plan: Pick<PlanView, "byId">, task: PlanTask): readonly TaskView[] {
  return task.blocked_by.map((id) => plan.byId.get(id)).filter((blocker): blocker is TaskView => blocker !== undefined);
}

/** The plan as the pane reads it. Pure: the plan is never changed. */
export function buildPlanView(plan: Plan): PlanView {
  const critical = new Set(plan.critical_path.task_ids);
  const tasks: TaskView[] = [];
  const phases: PhaseView[] = plan.phases.map((phase, phaseIndex) => {
    const phaseCode = `P${phaseIndex + 1}`;
    const taskViews = phase.tasks.map((task): TaskView => {
      const view: TaskView = {
        task,
        code: `T${tasks.length + 1}`,
        phaseIndex,
        phaseCode,
        critical: critical.has(task.id),
      };
      tasks.push(view);
      return view;
    });
    return {
      phase,
      code: phaseCode,
      points: taskViews.reduce((sum, view) => sum + view.task.estimate, 0),
      tasks: taskViews,
    };
  });
  return {
    phases,
    tasks,
    byId: new Map(tasks.map((view) => [view.task.id, view])),
    summary: {
      phases: phases.length,
      tasks: tasks.length,
      points: phases.reduce((sum, phase) => sum + phase.points, 0),
      criticalPoints: plan.critical_path.points,
      criticalTasks: plan.critical_path.task_ids.length,
    },
  };
}
