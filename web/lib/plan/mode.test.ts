import { describe, expect, it } from "vitest";

import { planOf, task } from "./fixtures";
import { planMode } from "./mode";

const plan = planOf([[task("a", 1)]]);

describe("planMode", () => {
  it("reviews while the run waits and the phases are not sent", () => {
    expect(planMode({ reviewing: true, reviewStatus: "idle", plan: null })).toBe("review");
    expect(planMode({ reviewing: true, reviewStatus: "failed", plan: undefined })).toBe("review");
  });

  it("says planning after Approve until the plan arrives", () => {
    expect(planMode({ reviewing: true, reviewStatus: "sent", plan: null })).toBe("planning");
    expect(planMode({ reviewing: false, reviewStatus: "sent", plan: null })).toBe("planning");
  });

  it("shows the plan once it exists", () => {
    expect(planMode({ reviewing: false, reviewStatus: "idle", plan })).toBe("plan");
    expect(planMode({ reviewing: true, reviewStatus: "sent", plan })).toBe("plan");
  });

  it("loads while the plan is unknown", () => {
    expect(planMode({ reviewing: false, reviewStatus: "idle", plan: undefined })).toBe("loading");
  });
});
