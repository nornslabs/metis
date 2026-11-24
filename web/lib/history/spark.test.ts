import { describe, expect, it } from "vitest";

import { SPARK_HEIGHT, SPARK_WIDTH, sparkGeometry } from "./spark";

describe("sparkGeometry", () => {
  it("returns null with fewer than two versions", () => {
    expect(sparkGeometry([])).toBeNull();
    expect(sparkGeometry([54])).toBeNull();
  });

  it("lists totals oldest first in the title", () => {
    expect(sparkGeometry([54, 63])?.title).toBe("v1 54 → v2 63");
    expect(sparkGeometry([61, 70, 76])?.title).toBe("v1 61 → v2 70 → v3 76");
  });

  it("points up when the latest total is above the first, down when below, flat when equal", () => {
    expect(sparkGeometry([54, 63])?.direction).toBe("up");
    expect(sparkGeometry([56, 52])?.direction).toBe("down");
    expect(sparkGeometry([60, 70, 60])?.direction).toBe("flat");
  });

  it("spreads points left to right inside the box, higher totals nearer the top", () => {
    const geometry = sparkGeometry([50, 70, 60]);

    const xs = geometry!.points.map((point) => point.x);
    expect(xs).toEqual([...xs].sort((a, b) => a - b));
    expect(geometry!.points.every((p) => p.x >= 0 && p.x <= SPARK_WIDTH && p.y >= 0 && p.y <= SPARK_HEIGHT)).toBe(true);
    expect(geometry!.points[1]!.y).toBeLessThan(geometry!.points[0]!.y);
  });

  it("keeps a flat trend inside the box", () => {
    const geometry = sparkGeometry([60, 60]);

    expect(geometry!.points.every((p) => p.y > 0 && p.y < SPARK_HEIGHT)).toBe(true);
  });
});
