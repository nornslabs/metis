import { describe, expect, it } from "vitest";

import { oldestFirst, outputsRunId } from "./runs-order";

describe("oldestFirst", () => {
  it("reverses the API's newest-first page without mutating it", () => {
    const page = [{ id: "c" }, { id: "b" }, { id: "a" }];
    expect(oldestFirst(page).map((run) => run.id)).toEqual(["a", "b", "c"]);
    expect(page.map((run) => run.id)).toEqual(["c", "b", "a"]);
  });
});

describe("outputsRunId", () => {
  it("is the oldest run, so a follow-up never takes the cards", () => {
    expect(outputsRunId([{ id: "a" }, { id: "b" }])).toBe("a");
  });

  it("is null without runs", () => {
    expect(outputsRunId([])).toBeNull();
  });
});
