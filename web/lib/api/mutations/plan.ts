import { ApiError } from "@/lib/api/errors";
import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import { PLAN_NOT_FOUND, planSchema, type Plan, type ReviewedPhase, type TaskPatch } from "@/lib/schemas/plan";

/** The idea's newest plan (`GET /v1/ideas/{id}/plan`), or `null` while there is none (`404 plan.not_found`). */
export async function fetchPlan(ideaId: string): Promise<Plan | null> {
  try {
    const result = await apiClient.GET("/v1/ideas/{idea_id}/plan", { params: { path: { idea_id: ideaId } } });
    return planSchema.parse(bodyOf(result));
  } catch (error: unknown) {
    if (error instanceof ApiError && error.code === PLAN_NOT_FOUND) return null;
    throw error;
  }
}

/** Saves one task's edits on plan `version` (`PATCH /v1/plans/{id}/tasks/{task_id}`); the answer is the whole plan. */
export async function patchPlanTask(planId: string, taskId: string, version: number, patch: TaskPatch): Promise<Plan> {
  const result = await apiClient.PATCH("/v1/plans/{plan_id}/tasks/{task_id}", {
    params: { path: { plan_id: planId, task_id: taskId } },
    body: { version, ...patch },
  });
  return planSchema.parse(bodyOf(result));
}

/** Answers the run's `phase_review` interrupt with the reviewed phases (`POST /v1/runs/{id}/resume`). */
export async function resumeWithPhases(runId: string, phases: readonly ReviewedPhase[]): Promise<void> {
  const result = await apiClient.POST("/v1/runs/{run_id}/resume", {
    params: { path: { run_id: runId } },
    body: { value: { phases: [...phases] } },
  });
  bodyOf(result);
}
