import { describe, expect, it } from "vitest";

import { outputStarts } from "./output-starts";

const step = (node: string) => ({ node, done: true, tools: [] });

describe("outputStarts", () => {
  it("is all false for a chat-only run on a fresh idea", () => {
    expect(outputStarts([], "interviewing")).toEqual({
      scoringStarted: false,
      researchStarted: false,
      specStarted: false,
      planStarted: false,
    });
  });

  it("follows the run's own steps", () => {
    const starts = outputStarts([step("researcher"), step("scorer")], "scoring");
    expect(starts.researchStarted).toBe(true);
    expect(starts.scoringStarted).toBe(true);
    expect(starts.specStarted).toBe(false);
  });

  it("counts the spec and plan once the idea is past them", () => {
    const starts = outputStarts([], "exported");
    expect(starts.specStarted).toBe(true);
    expect(starts.planStarted).toBe(true);
  });
});
