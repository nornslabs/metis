import type { ReviewStatus } from "@/lib/plan/phase-review";
import type { Plan } from "@/lib/schemas/plan";

export type PlanMode = "review" | "planning" | "plan" | "loading";

interface ModeInput {
  /** The run waits on `phase_review`. */
  reviewing: boolean;
  reviewStatus: ReviewStatus;
  /** The plan, `null` when none exists yet, `undefined` while it loads. */
  plan: Plan | null | undefined;
}

/**
 * What the Plan pane shows: the phase review while the run waits on it; "Planning tasks…" after
 * Approve until the plan arrives; the plan once it exists.
 */
export function planMode({ reviewing, reviewStatus, plan }: ModeInput): PlanMode {
  if (reviewing && reviewStatus !== "sent") return "review";
  if (plan) return "plan";
  if (plan === undefined && !reviewing && reviewStatus !== "sent") return "loading";
  return "planning";
}
