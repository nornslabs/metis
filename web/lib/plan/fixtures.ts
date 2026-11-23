import type { Plan, PlanTask } from "@/lib/schemas/plan";

export const task = (id: string, estimate: number, blockedBy: readonly string[] = [], title = `Task ${id}`): PlanTask => ({
  id,
  position: 0,
  title,
  description: `About ${id}`,
  estimate,
  labels: [],
  parent_task_id: null,
  blocked_by: [...blockedBy],
});

/** A plan whose phases hold the given tasks; positions follow list order. */
export function planOf(phases: readonly (readonly PlanTask[])[], criticalIds: readonly string[] = [], points = 0): Plan {
  return {
    id: "plan1",
    idea_id: "idea1",
    spec_version_id: "sv1",
    status: "draft",
    version: 1,
    ready_at: null,
    created_at: "2026-11-23T10:00:00Z",
    updated_at: "2026-11-23T10:00:00Z",
    phases: phases.map((tasks, index) => ({
      id: `ph${index + 1}`,
      position: index,
      name: `Phase ${index + 1}`,
      goal: "Goal",
      exit_criteria: "Done",
      tasks: tasks.map((entry, position) => ({ ...entry, position })),
    })),
    critical_path: { task_ids: [...criticalIds], points },
  };
}
