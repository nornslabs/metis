import { describe, expect, it } from "vitest";

import { FOLLOW_THRESHOLD_PX, distanceFromBottom, shouldFollow } from "./scroll";

describe("distanceFromBottom", () => {
  it("is zero at the bottom", () => {
    expect(distanceFromBottom(1000, 600, 400)).toBe(0);
  });

  it("grows as the reader scrolls up", () => {
    expect(distanceFromBottom(1000, 200, 400)).toBe(400);
  });
});

describe("shouldFollow", () => {
  it("follows a reader at the bottom or close to it", () => {
    expect(shouldFollow(0, false)).toBe(true);
    expect(shouldFollow(FOLLOW_THRESHOLD_PX, false)).toBe(true);
  });

  it("leaves a reader who scrolled up alone", () => {
    expect(shouldFollow(FOLLOW_THRESHOLD_PX + 1, false)).toBe(false);
  });

  it("always follows a message the reader just sent", () => {
    expect(shouldFollow(2000, true)).toBe(true);
  });
});
