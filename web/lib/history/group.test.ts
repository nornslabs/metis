import { describe, expect, it } from "vitest";

import { activityGroup, groupByActivity } from "./group";

const NOW = new Date(2026, 10, 23, 15, 0);

function daysBefore(days: number, hour = 9): string {
  return new Date(2026, 10, 23 - days, hour).toISOString();
}

describe("activityGroup", () => {
  it("puts any time today in Today, even earlier than now", () => {
    expect(activityGroup(daysBefore(0, 0), NOW)).toBe("Today");
  });

  it("puts the six days before today in This week", () => {
    expect(activityGroup(daysBefore(1, 23), NOW)).toBe("This week");
    expect(activityGroup(daysBefore(6), NOW)).toBe("This week");
  });

  it("puts anything older in Earlier", () => {
    expect(activityGroup(daysBefore(7), NOW)).toBe("Earlier");
    expect(activityGroup(daysBefore(90), NOW)).toBe("Earlier");
  });

  it("treats a time in the future as Today", () => {
    expect(activityGroup(daysBefore(-1), NOW)).toBe("Today");
  });
});

describe("groupByActivity", () => {
  it("keeps order, in Today / This week / Earlier order, and leaves empty groups out", () => {
    const rows = [
      { id: "a", activeAt: daysBefore(0) },
      { id: "b", activeAt: daysBefore(10) },
      { id: "c", activeAt: daysBefore(11) },
    ];

    const groups = groupByActivity(rows, NOW);

    expect(groups.map((g) => g.group)).toEqual(["Today", "Earlier"]);
    expect(groups[1]!.rows.map((r) => r.id)).toEqual(["b", "c"]);
  });

  it("returns no groups for no rows", () => {
    expect(groupByActivity([], NOW)).toEqual([]);
  });
});
