import { describe, expect, it } from "vitest";

import { relativeTime } from "./relative-time";

const NOW = new Date("2026-11-23T12:00:00Z");

function ago(ms: number): string {
  return new Date(NOW.getTime() - ms).toISOString();
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

describe("relativeTime", () => {
  it.each([
    [30_000, "just now"],
    [5 * MINUTE, "5 min ago"],
    [HOUR, "1 hour ago"],
    [3 * HOUR, "3 hours ago"],
    [DAY, "1 day ago"],
    [2 * DAY, "2 days ago"],
    [14 * DAY, "2 weeks ago"],
    [45 * DAY, "1 month ago"],
    [400 * DAY, "1 year ago"],
  ])("%d ms ago reads %s", (elapsed, expected) => {
    expect(relativeTime(ago(elapsed), NOW)).toBe(expected);
  });

  it("reads just now for a time in the future", () => {
    expect(relativeTime(ago(-5 * MINUTE), NOW)).toBe("just now");
  });
});
