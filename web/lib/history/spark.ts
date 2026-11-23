export const SPARK_WIDTH = 34;
export const SPARK_HEIGHT = 12;
/** Room kept at each edge so a 3px point stays inside the box. */
const EDGE = 1;
/** Headroom above and below the data, so a flat trend sits mid-box. */
const HEADROOM = 4;
const MIN_VERSIONS = 2;

export type SparkDirection = "up" | "down" | "flat";

export interface SparkPoint {
  x: number;
  y: number;
}

export interface SparkGeometry {
  points: readonly SparkPoint[];
  direction: SparkDirection;
  /** Text for `<title>`: "v1 54 → v2 63". */
  title: string;
}

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

/** The trend of score totals, oldest first, or null with fewer than two versions. */
export function sparkGeometry(totals: readonly number[]): SparkGeometry | null {
  if (totals.length < MIN_VERSIONS) return null;
  const low = Math.min(...totals) - HEADROOM;
  const high = Math.max(...totals) + HEADROOM;
  const points = totals.map((total, index) => ({
    x: round(EDGE + (index * (SPARK_WIDTH - 2 * EDGE)) / (totals.length - 1)),
    y: round(SPARK_HEIGHT - EDGE - ((total - low) / (high - low)) * (SPARK_HEIGHT - 2 * EDGE)),
  }));
  const change = totals[totals.length - 1]! - totals[0]!;
  return {
    points,
    direction: change > 0 ? "up" : change < 0 ? "down" : "flat",
    title: totals.map((total, index) => `v${index + 1} ${total}`).join(" → "),
  };
}
