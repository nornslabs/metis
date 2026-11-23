import { describe, expect, it } from "vitest";

import { PLAN_STAGES, SPEC_STAGES } from "./stages";

describe("stage sets", () => {
  it("has a spec from the draft on, but a plan only from planning", () => {
    expect(SPEC_STAGES.has("spec_draft")).toBe(true);
    expect(PLAN_STAGES.has("spec_draft")).toBe(false);
    expect(PLAN_STAGES.has("planning")).toBe(true);
  });
});
