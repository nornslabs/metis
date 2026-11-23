/**
 * Viewport widths (px) above which the frame draws its edges and the column guides. They mirror
 * the `compact` and `guides` breakpoints in `app/globals.css`; keep them in sync.
 */
export const FRAME_EDGES_MIN_WIDTH = 700;
export const COLUMN_GUIDES_MIN_WIDTH = 820;

export type FrameVerticalKind = "frame" | "guide";

export interface FrameMeasure {
  viewportWidth: number;
  /** The bordered safe area. */
  safe: { left: number; right: number };
  /** The chat column, or null when the page has none. */
  column: { left: number; right: number } | null;
  /** Bottom edge of the header. */
  headerBottom: number;
  /** Top edge of the footer. */
  footerTop: number;
  /** Top edge of the composer, or null when the page has none. */
  bandTop: number | null;
}

export interface FrameVertical {
  x: number;
  kind: FrameVerticalKind;
  /** Which side of its box the line borders; an `end` line is drawn inside the box's edge. */
  edge: "start" | "end";
}

export interface FrameTick {
  x: number;
  y: number;
}

export interface FrameLines {
  verticals: readonly FrameVertical[];
  /** Top edge of the input band, or null on a page without a composer. */
  bandY: number | null;
  /** A `+` at every vertical line crossing the header line, the footer line and the input band. */
  ticks: readonly FrameTick[];
}

/**
 * Turns measured rects into the lines the frame draws. Under 820px the column guides go, under
 * 700px the frame edges go too (the full-width frame has no side borders to cross).
 */
export function computeFrameLines(measure: FrameMeasure): FrameLines {
  const { viewportWidth, safe, column, headerBottom, footerTop, bandTop } = measure;
  const verticals: FrameVertical[] = [];
  if (viewportWidth > FRAME_EDGES_MIN_WIDTH) {
    verticals.push(
      { x: safe.left, kind: "frame", edge: "start" },
      { x: safe.right, kind: "frame", edge: "end" },
    );
  }
  if (column && viewportWidth > COLUMN_GUIDES_MIN_WIDTH) {
    // A column as wide as the frame has its guides on the frame's own edges: draw those once.
    const onFrameEdge = (x: number) => verticals.some((vertical) => Math.abs(vertical.x - x) < 1);
    if (!onFrameEdge(column.left)) verticals.push({ x: column.left, kind: "guide", edge: "start" });
    if (!onFrameEdge(column.right)) verticals.push({ x: column.right, kind: "guide", edge: "end" });
  }
  const ys = bandTop === null ? [headerBottom, footerTop] : [headerBottom, footerTop, bandTop];
  const ticks = verticals.flatMap(({ x }) => ys.map((y) => ({ x, y })));
  return { verticals, bandY: bandTop, ticks };
}

/** True when two results draw the same lines; keeps the hook from re-rendering on equal measures. */
export function sameFrameLines(a: FrameLines | null, b: FrameLines | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
