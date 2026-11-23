import { describe, expect, it } from "vitest";

import { ASCII_RAMP, gridFromPixels, rampChar } from "./ascii-owl";

/** An RGBA buffer where each pixel's red channel comes from `value(x, y)`. */
function buffer(width: number, height: number, value: (x: number, y: number) => number): Uint8ClampedArray {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) data[(y * width + x) * 4] = value(x, y);
  }
  return data;
}

describe("rampChar", () => {
  it("maps the darkest brightness to a space and the brightest to @", () => {
    expect(rampChar(0)).toBe(" ");
    expect(rampChar(1)).toBe("@");
  });

  it("clamps values outside 0 to 1", () => {
    expect(rampChar(-3)).toBe(" ");
    expect(rampChar(7)).toBe("@");
  });

  it("walks the whole ramp in order", () => {
    const steps = ASCII_RAMP.length - 1;
    const chars = Array.from({ length: steps + 1 }, (_, step) => rampChar(step / steps)).join("");
    expect(chars).toBe(ASCII_RAMP);
  });
});

describe("gridFromPixels", () => {
  const grid = { width: 8, cols: 2, rows: 2, cellWidth: 4, cellHeight: 4 };

  it("renders one character per cell and a line per row", () => {
    const data = buffer(8, 8, (x, y) => (x < 4 && y < 4 ? 255 : 0));
    expect(gridFromPixels(data, grid)).toBe("@\n\n");
  });

  it("trims trailing spaces but keeps leading ones", () => {
    const data = buffer(8, 8, (x) => (x >= 4 ? 255 : 0));
    expect(gridFromPixels(data, grid)).toBe(" @\n @\n");
  });

  it("averages the pixels sampled inside a cell", () => {
    const data = buffer(8, 8, (_, y) => (y % 4 < 2 ? 255 : 0));
    expect(gridFromPixels(data, { ...grid, cols: 1 })).toBe(`${rampChar(0.5)}\n${rampChar(0.5)}\n`);
  });

  it("does not change its input", () => {
    const data = buffer(8, 8, (x, y) => x * 10 + y);
    const before = Array.from(data);
    gridFromPixels(data, grid);
    expect(Array.from(data)).toEqual(before);
  });
});
