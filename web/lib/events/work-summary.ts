import { countOf } from "@/lib/text/count";

import { RESEARCHER_NODE } from "./activity";
import type { RunStep } from "./reducer";

/**
 * The one line the chat keeps for a block of work that is not running now: "Researched 6 sources"
 * when the Researcher ran and its sources are known, else "Worked through 3 steps" (a step a failed
 * or stopped run never finished still counts), or "Skipped 1 step" when every step was skipped.
 * `null` when there are no steps.
 */
export function workSummaryLine(steps: readonly RunStep[], sourceCount: number | null): string | null {
  if (steps.length === 0) return null;
  const worked = steps.filter((step) => !step.skipped);
  if (worked.length === 0) return `Skipped ${countOf(steps.length, "step")}`;
  const researched = worked.some((step) => step.node === RESEARCHER_NODE);
  if (researched && sourceCount !== null && sourceCount > 0) return `Researched ${countOf(sourceCount, "source")}`;
  return `Worked through ${countOf(worked.length, "step")}`;
}

/** The counter in the working bar: finished steps over steps seen so far, e.g. "2/3". `null` before any step. */
export function stepCounter(steps: readonly RunStep[]): string | null {
  if (steps.length === 0) return null;
  const done = steps.filter((step) => step.done).length;
  return `${Math.min(done + 1, steps.length)}/${steps.length}`;
}
