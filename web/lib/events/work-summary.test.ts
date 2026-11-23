import { describe, expect, it } from "vitest";

import { stepCounter, workSummaryLine } from "./work-summary";

const step = (node: string, done: boolean, skipped = false) => ({ node, done, skipped, tools: [] });

describe("workSummaryLine", () => {
  it("says how many sources the Researcher used", () => {
    expect(workSummaryLine([step("researcher", true)], 6)).toBe("Researched 6 sources");
    expect(workSummaryLine([step("researcher", true)], 1)).toBe("Researched 1 source");
  });

  it("counts the finished steps when there are no sources to name", () => {
    expect(workSummaryLine([step("interviewer", true), step("scorer", true)], null)).toBe("Worked through 2 steps");
    expect(workSummaryLine([step("researcher", true)], 0)).toBe("Worked through 1 step");
  });

  it("counts a step a stopped run never finished, but not a skipped one", () => {
    expect(workSummaryLine([step("interviewer", false), step("researcher", true, true)], null)).toBe(
      "Worked through 1 step",
    );
  });

  it("says so when every step was skipped, and is null with no steps", () => {
    expect(workSummaryLine([step("researcher", true, true)], null)).toBe("Skipped 1 step");
    expect(workSummaryLine([], 4)).toBeNull();
  });
});

describe("stepCounter", () => {
  it("shows the step in progress over the steps seen", () => {
    expect(stepCounter([step("a", true), step("b", false), step("c", false)])).toBe("2/3");
  });

  it("never passes the total, and is null before any step", () => {
    expect(stepCounter([step("a", true), step("b", true)])).toBe("2/2");
    expect(stepCounter([])).toBeNull();
  });
});
