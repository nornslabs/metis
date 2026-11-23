import { describe, expect, it } from "vitest";

import { countQuestions, splitSegments } from "./segments";

describe("splitSegments", () => {
  it("puts each segment before its question and the last one in the tail", () => {
    expect(splitSegments(["a", "X", "Y"], 2)).toEqual({ leads: ["a", "X"], tail: "Y" });
  });

  it("keeps all text in the tail when there are no question rows", () => {
    expect(splitSegments(["hello"], 0)).toEqual({ leads: [], tail: "hello" });
  });

  it("joins segments that have no question row to sit before", () => {
    expect(splitSegments(["a", "b", "c"], 1)).toEqual({ leads: ["a"], tail: "b\n\nc" });
  });

  it("has fewer leads than questions when the run wrote less", () => {
    expect(splitSegments([""], 2)).toEqual({ leads: [""], tail: "" });
  });
});

describe("countQuestions", () => {
  it("counts agent messages", () => {
    const base = { key: "k", runId: "r", text: "t" };
    expect(countQuestions([{ role: "agent", ...base }, { role: "user", ...base }, { role: "agent", ...base }])).toBe(2);
  });
});
