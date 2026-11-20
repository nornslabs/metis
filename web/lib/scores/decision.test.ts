import { describe, expect, test } from "vitest";

import { MAX_ACCEPTED_SUGGESTIONS, acceptedFor, buildResume, reviseSchema } from "./decision";
import type { Suggestion } from "./view";

function suggestion(id: string, scoreRunId: string, status: Suggestion["status"]): Suggestion {
  return { id, score_run_id: scoreRunId, status } as Suggestion;
}

describe("reviseSchema", () => {
  test("trims and accepts 10 to 10,000 characters", () => {
    expect(reviseSchema.safeParse({ text: "  a revised idea  " }).data).toEqual({ text: "a revised idea" });
  });

  test("refuses text that is too short or too long", () => {
    expect(reviseSchema.safeParse({ text: "short" }).success).toBe(false);
    expect(reviseSchema.safeParse({ text: "x".repeat(10_001) }).success).toBe(false);
  });
});

describe("acceptedFor", () => {
  test("keeps only accepted suggestions of that score run, at most five", () => {
    const many = Array.from({ length: 7 }, (_, index) => suggestion(`a${index}`, "run-1", "accepted"));
    const list = [suggestion("x", "run-2", "accepted"), suggestion("y", "run-1", "dismissed"), ...many];
    expect(acceptedFor(list, "run-1").map((entry) => entry.id)).toEqual(many.slice(0, MAX_ACCEPTED_SUGGESTIONS).map((entry) => entry.id));
  });
});

describe("buildResume", () => {
  test("revise carries the trimmed text and the accepted ids", () => {
    expect(buildResume("revise", "  new text here  ", [suggestion("a", "r", "accepted")])).toEqual({
      decision: "revise",
      revised_text: "new text here",
      accepted_suggestion_ids: ["a"],
    });
  });

  test("continue and stop carry nothing else", () => {
    expect(buildResume("continue")).toEqual({ decision: "continue", accepted_suggestion_ids: [] });
    expect(buildResume("stop")).toEqual({ decision: "stop", accepted_suggestion_ids: [] });
  });
});
