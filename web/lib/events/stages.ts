/** From the spec draft on, the idea has a spec to read. */
export const SPEC_STAGES: ReadonlySet<string> = new Set([
  "spec_draft",
  "spec_confirmed",
  "planning",
  "exported",
]);

/** From planning on, the idea has phases or a plan to read. */
export const PLAN_STAGES: ReadonlySet<string> = new Set([
  "planning",
  "exported",
]);
