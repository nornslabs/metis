import { describe, expect, test } from "vitest";

import { hasArrived, nextBaseline, pickAutoOpen } from "@/lib/workspace/live-arrival";

describe("nextBaseline", () => {
  test("waits for the first load to settle", () => {
    expect(nextBaseline(null, "a", false, false)).toBeNull();
  });

  test("records whether the output was absent at the first settled load", () => {
    expect(nextBaseline(null, "a", true, false)).toEqual({ scope: "a", absent: true });
    expect(nextBaseline(null, "a", true, true)).toEqual({ scope: "a", absent: false });
  });

  test("keeps the baseline once it is set", () => {
    const first = nextBaseline(null, "a", true, false);
    expect(nextBaseline(first, "a", true, true)).toBe(first);
  });

  test("starts over for another idea", () => {
    const first = nextBaseline(null, "a", true, true);
    expect(nextBaseline(first, "b", true, false)).toEqual({ scope: "b", absent: true });
  });
});

describe("hasArrived", () => {
  test("is true for an output that appeared after a load that found none", () => {
    expect(hasArrived({ scope: "a", absent: true }, "a", true)).toBe(true);
  });

  test("is false for an output that was there at load, or is still missing", () => {
    expect(hasArrived({ scope: "a", absent: false }, "a", true)).toBe(false);
    expect(hasArrived({ scope: "a", absent: true }, "a", false)).toBe(false);
  });

  test("is false before the first load settled or for another scope", () => {
    expect(hasArrived(null, "a", true)).toBe(false);
    expect(hasArrived({ scope: "b", absent: true }, "a", true)).toBe(false);
  });
});

describe("pickAutoOpen", () => {
  const open = { alreadyOpened: false, narrow: false, outputOpen: false };

  test("opens the first output that arrived", () => {
    expect(pickAutoOpen(["score", "suggestions"], open)).toBe("score");
  });

  test("does nothing when nothing arrived", () => {
    expect(pickAutoOpen([], open)).toBeNull();
  });

  test("never opens under 820px, while the panel is open, or a second time", () => {
    expect(pickAutoOpen(["score"], { ...open, narrow: true })).toBeNull();
    expect(pickAutoOpen(["score"], { ...open, outputOpen: true })).toBeNull();
    expect(pickAutoOpen(["suggestions"], { ...open, alreadyOpened: true })).toBeNull();
  });
});
