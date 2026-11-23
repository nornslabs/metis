import { z } from "zod";

/** Error codes the plan routes answer with (`server-context.md`, error catalog). */
export const PLAN_CONFLICT = "plan.conflict";
export const PLAN_NOT_EDITABLE = "plan.invalid_transition";
export const PLAN_NOT_FOUND = "plan.not_found";

/** The estimates a task can have (Fibonacci, as the planning module allows). */
export const ESTIMATES = [1, 2, 3, 5, 8] as const;

/** Limits of the planning module (`PhaseInput`, `TaskInput`), trimmed text. */
export const PHASE_LIMITS = { maxPhases: 12, name: 120, text: 1000 } as const;
export const TASK_TITLE_MAX = 200;

const taskSchema = z.object({
  id: z.string(),
  position: z.number().int().nonnegative(),
  title: z.string(),
  description: z.string(),
  estimate: z.number().int(),
  labels: z.array(z.string()),
  parent_task_id: z.string().nullable(),
  blocked_by: z.array(z.string()),
});

const phaseSchema = z.object({
  id: z.string(),
  position: z.number().int().nonnegative(),
  name: z.string(),
  goal: z.string(),
  exit_criteria: z.string(),
  tasks: z.array(taskSchema),
});

/** `GET /v1/ideas/{id}/plan` and the answer of every plan edit: phases → tasks → blockers, and the critical path. */
export const planSchema = z.object({
  id: z.string(),
  idea_id: z.string(),
  spec_version_id: z.string(),
  status: z.enum(["draft", "ready"]),
  version: z.number().int().positive(),
  ready_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  phases: z.array(phaseSchema),
  critical_path: z.object({ task_ids: z.array(z.string()), points: z.number() }),
});

export type PlanTask = z.infer<typeof taskSchema>;
export type PlanPhase = z.infer<typeof phaseSchema>;
export type Plan = z.infer<typeof planSchema>;

/** One phase as the review shows it and the resume answer sends it. */
export const reviewedPhaseSchema = z.object({
  name: z.string(),
  goal: z.string(),
  exit_criteria: z.string(),
});

export type ReviewedPhase = z.infer<typeof reviewedPhaseSchema>;

/** A task's title as the user may save it. */
export const taskTitleSchema = z.string().trim().min(1, "A task needs a title.").max(TASK_TITLE_MAX, `Keep the title under ${TASK_TITLE_MAX} characters.`);

/** What a task edit can change (the planning module's `TaskPatch`, without position). */
export type TaskPatch = {
  readonly title?: string;
  readonly estimate?: number;
  readonly phase_id?: string;
};
