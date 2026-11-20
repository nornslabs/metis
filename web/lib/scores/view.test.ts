import { describe, expect, test } from "vitest";

import { barPercent, chartPoints, daysAgoLabel, formatPoints, groupByScoreRun, type ScoreRunSummary, type Suggestion } from "./view";

const NOW = new Date("2026-11-20T12:00:00Z");

function summary(id: string, total: number, createdAt: string): ScoreRunSummary {
  return {
    id,
    total,
    band: total >= 75 ? "build" : total >= 55 ? "promising" : "advise",
    created_at: createdAt,
    idea_id: "i",
    rubric_version: 1,
    run_id: "r",
    trigger: "manual",
  };
}

describe("daysAgoLabel", () => {
  test("says today within a day", () => {
    expect(daysAgoLabel("2026-11-20T01:00:00Z", NOW)).toBe("today");
  });

  test("says 1 day ago, then N days ago", () => {
    expect(daysAgoLabel("2026-11-19T10:00:00Z", NOW)).toBe("1 day ago");
    expect(daysAgoLabel("2026-11-10T12:00:00Z", NOW)).toBe("10 days ago");
  });

  test("gives nothing for an unreadable date", () => {
    expect(daysAgoLabel("not a date", NOW)).toBe("");
  });
});

describe("bars", () => {
  test("a mark out of ten is a percentage width, clamped", () => {
    expect(barPercent(7)).toBe(70);
    expect(barPercent(12)).toBe(100);
    expect(barPercent(-1)).toBe(0);
  });

  test("points show one decimal only when needed", () => {
    expect(formatPoints(18)).toBe("18");
    expect(formatPoints(17.5)).toBe("17.5");
  });
});

describe("chartPoints", () => {
  test("orders the newest-first history oldest first and puts a higher total higher up", () => {
    const points = chartPoints([summary("c", 80, "2026-11-20T00:00:00Z"), summary("b", 60, "2026-11-19T00:00:00Z"), summary("a", 40, "2026-11-18T00:00:00Z")]);
    expect(points.map((point) => point.id)).toEqual(["a", "b", "c"]);
    expect(points.map((point) => point.x)).toEqual([0, 50, 100]);
    expect(points.map((point) => point.y)).toEqual([60, 40, 20]);
  });

  test("a single run sits in the middle", () => {
    expect(chartPoints([summary("a", 50, "2026-11-18T00:00:00Z")])[0]?.x).toBe(50);
  });
});

describe("groupByScoreRun", () => {
  test("keeps the server's order, one group per score run", () => {
    const make = (id: string, scoreRunId: string) => ({ id, score_run_id: scoreRunId }) as Suggestion;
    const groups = groupByScoreRun([make("1", "new"), make("2", "new"), make("3", "old")]);
    expect(groups.map((group) => group.map((entry) => entry.id))).toEqual([["1", "2"], ["3"]]);
  });
});
