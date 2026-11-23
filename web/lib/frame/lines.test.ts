import { describe, expect, test } from "vitest";

import { computeFrameLines, sameFrameLines, type FrameMeasure } from "./lines";

const WIDE: FrameMeasure = {
  viewportWidth: 1440,
  safe: { left: 80, right: 1360 },
  column: { left: 340, right: 1100 },
  headerBottom: 44,
  footerTop: 868,
  bandTop: 760,
};

describe("computeFrameLines", () => {
  test("puts a tick on every vertical crossing the header, footer and input band", () => {
    // Arrange / Act
    const lines = computeFrameLines(WIDE);

    // Assert
    expect(lines.verticals.map((v) => v.x)).toEqual([80, 1360, 340, 1100]);
    expect(lines.verticals.map((v) => v.edge)).toEqual(["start", "end", "start", "end"]);
    expect(lines.ticks).toHaveLength(12);
    expect(lines.ticks).toContainEqual({ x: 340, y: 760 });
    expect(lines.ticks).toContainEqual({ x: 1360, y: 44 });
  });

  test("leaves out the band ticks when the page has no composer", () => {
    const lines = computeFrameLines({ ...WIDE, bandTop: null });

    expect(lines.bandY).toBeNull();
    expect(lines.ticks).toHaveLength(8);
  });

  test("hides the column guides at 820px and below", () => {
    const lines = computeFrameLines({ ...WIDE, viewportWidth: 820 });

    expect(lines.verticals.every((v) => v.kind === "frame")).toBe(true);
  });

  test("hides the frame edges at 700px and below", () => {
    const lines = computeFrameLines({ ...WIDE, viewportWidth: 375, safe: { left: 0, right: 375 } });

    expect(lines.verticals).toEqual([]);
    expect(lines.ticks).toEqual([]);
  });

  test("draws a guide that falls on a frame edge only once", () => {
    const lines = computeFrameLines({ ...WIDE, viewportWidth: 1000, safe: { left: 32, right: 968 }, column: { left: 32, right: 968 } });

    expect(lines.verticals.map((v) => v.kind)).toEqual(["frame", "frame"]);
    expect(lines.ticks).toHaveLength(6);
  });

  test("draws no guides when there is no column", () => {
    const lines = computeFrameLines({ ...WIDE, column: null });

    expect(lines.verticals.map((v) => v.kind)).toEqual(["frame", "frame"]);
  });
});

describe("sameFrameLines", () => {
  test("is true for equal results and false once a line moves", () => {
    const a = computeFrameLines(WIDE);

    expect(sameFrameLines(a, computeFrameLines(WIDE))).toBe(true);
    expect(sameFrameLines(a, computeFrameLines({ ...WIDE, bandTop: 700 }))).toBe(false);
    expect(sameFrameLines(null, a)).toBe(false);
  });
});
