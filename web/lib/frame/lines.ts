/**
 * Viewport widths (px) above which the frame draws its edges and the column guides. They mirror
 * the `compact` and `guides` breakpoints in `app/globals.css`; keep them in sync.
 */
export const FRAME_EDGES_MIN_WIDTH = 700;
export const COLUMN_GUIDES_MIN_WIDTH = 820;
/** From this width the side panels push the chat pane; under it they are overlays with no edge lines. */
export const PANELS_PUSH_MIN_WIDTH = 820;
/** Ticks on the input band tolerate this much (px) at its ends, as the line sits on a panel edge. */
const BAND_END_TOLERANCE_PX = 2;

export type FrameVerticalKind = "frame" | "guide" | "panel";

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
  /** Right edge of the open history panel, or null when it is closed. */
  historyRight: number | null;
  /** Left edge of the open output panel, or null when it is closed. */
  outputLeft: number | null;
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
  /** Where the input band starts and ends: between the open panels, else the viewport's edges. */
  bandX: { start: number; end: number };
  /** A `+` at every vertical line crossing the header line, the footer line and the input band. */
  ticks: readonly FrameTick[];
}

/**
 * Turns measured rects into the lines the frame draws. Under 820px the column guides and the panel
 * edges go, under 700px the frame edges go too (the full-width frame has no side borders to cross).
 * Panel edges draw their own borders; here they only take part in the ticks and the input band.
 */
export function computeFrameLines(measure: FrameMeasure): FrameLines {
  const { viewportWidth, safe, column, headerBottom, footerTop, bandTop, historyRight, outputLeft } = measure;
  const verticals: FrameVertical[] = [];
  // A line is drawn once: a later one on the same x (a guide on a frame or panel edge) is dropped.
  const addVertical = (vertical: FrameVertical) => {
    if (!verticals.some((existing) => Math.abs(existing.x - vertical.x) < 1)) verticals.push(vertical);
  };
  if (viewportWidth > FRAME_EDGES_MIN_WIDTH) {
    addVertical({ x: safe.left, kind: "frame", edge: "start" });
    addVertical({ x: safe.right, kind: "frame", edge: "end" });
  }
  const pushing = viewportWidth >= PANELS_PUSH_MIN_WIDTH;
  if (pushing && historyRight !== null) addVertical({ x: historyRight, kind: "panel", edge: "end" });
  if (pushing && outputLeft !== null) addVertical({ x: outputLeft, kind: "panel", edge: "start" });
  if (column && viewportWidth > COLUMN_GUIDES_MIN_WIDTH) {
    addVertical({ x: column.left, kind: "guide", edge: "start" });
    addVertical({ x: column.right, kind: "guide", edge: "end" });
  }
  const bandX = {
    start: pushing && historyRight !== null ? historyRight : 0,
    end: pushing && outputLeft !== null ? outputLeft : viewportWidth,
  };

  const onBand = (x: number) =>
    x >= bandX.start - BAND_END_TOLERANCE_PX && x <= bandX.end + BAND_END_TOLERANCE_PX;
  const ticks = verticals.flatMap(({ x }) => {
    const ys = bandTop !== null && onBand(x) ? [headerBottom, footerTop, bandTop] : [headerBottom, footerTop];
    return ys.map((y) => ({ x, y }));
  });
  return { verticals, bandY: bandTop, bandX, ticks };
}

/** True when two results draw the same lines; keeps the hook from re-rendering on equal measures. */
export function sameFrameLines(a: FrameLines | null, b: FrameLines | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
