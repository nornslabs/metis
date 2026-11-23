import { describe, expect, test } from "vitest";

import { appliedIn, deltaText, isWeakMark, scoreVersions, versionAfter } from "@/lib/scores/versions";
import type { ScoreRunSummary } from "@/lib/scores/view";

function run(id: string, total: number, trigger: ScoreRunSummary["trigger"] = "manual"): ScoreRunSummary {
  return { id, idea_id: "i", run_id: "r", rubric_version: 1, total, band: "promising", trigger, created_at: "2026-11-20T10:00:00Z" };
}

// Newest first, as the server sends it.
const HISTORY = [run("c", 70), run("b", 63), run("a", 56, "scheduled")];

describe("scoreVersions", () => {
  test("numbers the oldest run v1 and keeps the newest first", () => {
    const versions = scoreVersions(HISTORY);
    expect(versions.map((version) => [version.id, version.number])).toEqual([["c", 3], ["b", 2], ["a", 1]]);
  });

  test("gives v1 no delta and the first-score note", () => {
    const first = scoreVersions(HISTORY).at(-1);
    expect(first?.delta).toBeNull();
    expect(first?.note).toBe("first score");
  });

  test("computes the change against the previous version", () => {
    const versions = scoreVersions(HISTORY);
    expect(versions.map((version) => version.delta)).toEqual([7, 7, null]);
  });

  test("returns nothing for an empty history", () => {
    expect(scoreVersions([])).toEqual([]);
  });
});

describe("deltaText", () => {
  test("shows a rise, a fall, and nothing for v1 or no change", () => {
    expect(deltaText(7)).toBe("▲ 7");
    expect(deltaText(-3)).toBe("▼ 3");
    expect(deltaText(0)).toBeNull();
    expect(deltaText(null)).toBeNull();
  });
});

describe("isWeakMark", () => {
  test("is true under 55 on the 100 scale", () => {
    expect(isWeakMark(5)).toBe(true);
    expect(isWeakMark(6)).toBe(false);
  });
});

describe("applied in a version", () => {
  const versions = scoreVersions(HISTORY);

  test("is the version after the advised score run", () => {
    expect(versionAfter(versions, "a")).toBe(2);
    expect(appliedIn({ status: "accepted", score_run_id: "a" }, versions)).toBe(2);
  });

  test("is null while the advised run is the newest", () => {
    expect(appliedIn({ status: "accepted", score_run_id: "c" }, versions)).toBeNull();
  });

  test("is null for a suggestion that is not accepted", () => {
    expect(appliedIn({ status: "open", score_run_id: "a" }, versions)).toBeNull();
    expect(appliedIn({ status: "dismissed", score_run_id: "a" }, versions)).toBeNull();
  });
});
