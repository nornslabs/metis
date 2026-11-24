import { describe, expect, it } from "vitest";

import { EDIT_VIEW, compareFrom, olderVersionNumbers, resolveView, shownNumber } from "@/lib/spec/view";

describe("resolveView", () => {
  it("keeps an older version", () => {
    expect(resolveView({ mode: "version", number: 1 }, 3)).toEqual({ mode: "version", number: 1 });
  });

  it("shows the newest version as the editor", () => {
    expect(resolveView({ mode: "version", number: 3 }, 3)).toBe(EDIT_VIEW);
  });

  it("keeps compare as it is", () => {
    expect(resolveView({ mode: "compare", from: 1 }, 3)).toEqual({ mode: "compare", from: 1 });
  });
});

describe("compareFrom", () => {
  it("starts from the version before the newest", () => {
    expect(compareFrom({ mode: "compare", from: null }, 4)).toBe(3);
    expect(compareFrom(EDIT_VIEW, 4)).toBe(3);
  });

  it("uses the chosen older version", () => {
    expect(compareFrom({ mode: "compare", from: 1 }, 4)).toBe(1);
  });

  it("falls back when the chosen version is no longer older", () => {
    expect(compareFrom({ mode: "compare", from: 4 }, 4)).toBe(3);
  });

  it("has nothing to compare with one version", () => {
    expect(compareFrom(EDIT_VIEW, 1)).toBeNull();
  });
});

describe("version helpers", () => {
  it("lists the older versions newest first", () => {
    expect(olderVersionNumbers(4)).toEqual([3, 2, 1]);
    expect(olderVersionNumbers(1)).toEqual([]);
  });

  it("marks the version the menu shows", () => {
    expect(shownNumber(EDIT_VIEW, 3)).toBe(3);
    expect(shownNumber({ mode: "version", number: 1 }, 3)).toBe(1);
    expect(shownNumber({ mode: "compare", from: null }, 3)).toBeNull();
  });
});
