import { describe, expect, test } from "vitest";

import { compareScores, formatDelta, inOrder } from "./diff";
import type { ScoreParam, ScoreRun } from "./view";

function run(total: number, marks: Partial<Record<ScoreParam, number>>, createdAt = "2026-11-18T00:00:00Z"): ScoreRun {
  return {
    id: String(total),
    total,
    band: "advise",
    created_at: createdAt,
    idea_id: "i",
    rubric_version: 1,
    run_id: "r",
    trigger: "manual",
    weights: {},
    params: Object.entries(marks).map(([param, raw]) => ({
      param: param as ScoreParam,
      raw: raw ?? 0,
      reason: `${param} ${raw}`,
      weight: 25,
      weighted: 0,
      confidence: 0.5,
      no_evidence: false,
      evidence: [],
    })),
  };
}

describe("compareScores", () => {
  test("gives each parameter's signed change with both reasons", () => {
    const result = compareScores(run(48, { uniqueness: 3, timing: 6 }), run(62, { uniqueness: 6, timing: 5 }));
    expect(result.totalDelta).toBe(14);
    expect(result.changes).toEqual([
      expect.objectContaining({ param: "uniqueness", label: "Uniqueness", before: 3, after: 6, delta: 3, beforeReason: "uniqueness 3", afterReason: "uniqueness 6" }),
      expect.objectContaining({ param: "timing", delta: -1 }),
    ]);
  });

  test("skips a parameter the earlier run did not have", () => {
    expect(compareScores(run(10, { timing: 1 }), run(20, { timing: 2, value: 4 })).changes).toHaveLength(1);
  });
});

describe("formatDelta", () => {
  test("uses a plus, a real minus and a plain zero", () => {
    expect([formatDelta(3), formatDelta(-2), formatDelta(0)]).toEqual(["+3", "−2", "0"]);
  });
});

describe("inOrder", () => {
  test("puts the older run first whichever way they were picked", () => {
    const older = run(1, {}, "2026-11-01T00:00:00Z");
    const newer = run(2, {}, "2026-11-02T00:00:00Z");
    expect(inOrder(newer, older)).toEqual([older, newer]);
  });
});
