import { nodeLabel, toolLabel } from "./labels";
import type { RunState } from "./reducer";

/** The Researcher's graph node (the server's `Specialist` value). */
export const RESEARCHER_NODE = "researcher";

/** The Scorer's graph node. */
export const SCORER_NODE = "scorer";

/**
 * What the run is doing now, for the shimmer: the running step's name, plus its latest tool call
 * ("Researching… web_search_exa"), else what the run is waiting for.
 */
export function runActivity(state: Pick<RunState, "status" | "steps">): string {
  const running = state.steps.findLast((step) => !step.done);
  if (!running) return state.status === "queued" ? "Starting…" : "Thinking…";
  const tool = running.tools.at(-1);
  const label = running.node === RESEARCHER_NODE ? "Researching…" : `${nodeLabel(running.node)}…`;
  return tool ? `${label} ${toolLabel(tool)}` : label;
}

/** How many Researcher steps have finished: when it grows, the research view is refetched. */
export function finishedResearchSteps(state: Pick<RunState, "steps">): number {
  return state.steps.filter((step) => step.node === RESEARCHER_NODE && step.done).length;
}
