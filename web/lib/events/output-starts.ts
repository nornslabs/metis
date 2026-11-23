import { ARCHITECT_NODE, PLANNER_NODE, RESEARCHER_NODE, SCORER_NODE } from "./activity";
import type { RunState } from "./reducer";
import { PLAN_STAGES, SPEC_STAGES } from "./stages";

/** Which outputs a run can have, for `OutputCards` (a card's data is only read once its step began). */
export type OutputStarts = {
  readonly scoringStarted: boolean;
  readonly researchStarted: boolean;
  readonly specStarted: boolean;
  readonly planStarted: boolean;
};

/** The run's own steps, plus the idea's stage for what a later run already produced. */
export function outputStarts(steps: RunState["steps"], stage: string): OutputStarts {
  const ran = (node: string) => steps.some((step) => step.node === node);
  return {
    scoringStarted: ran(SCORER_NODE),
    researchStarted: ran(RESEARCHER_NODE),
    specStarted: SPEC_STAGES.has(stage) || ran(ARCHITECT_NODE),
    planStarted: PLAN_STAGES.has(stage) || ran(PLANNER_NODE),
  };
}
