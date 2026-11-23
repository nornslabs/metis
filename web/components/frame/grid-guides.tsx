"use client";

import { CrossTick } from "./cross-tick";
import { useFrameLines } from "./use-frame-lines";

/** Line width (px); an `end` guide is drawn this far inside its box's edge. */
const LINE_WIDTH_PX = 1;

/**
 * Column guides, the full-width input band and the `+` ticks where lines cross, all placed from
 * measured positions so they follow the layout (ui-context.md, Layout: Frame and Grid).
 */
export function GridGuides() {
  const lines = useFrameLines();
  if (!lines) return null;

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0">
      {lines.verticals
        .filter(({ kind }) => kind === "guide")
        .map(({ x, edge }) => (
          <span
            key={x}
            style={{ left: edge === "end" ? x - LINE_WIDTH_PX : x }}
            className="absolute inset-y-0 w-px bg-border"
          />
        ))}
      {lines.bandY === null ? null : (
        // The composer starts at `bandY` and paints over its own first row, so the line is the row above.
        <span style={{ top: lines.bandY - LINE_WIDTH_PX }} className="absolute inset-x-0 h-px bg-border" />
      )}
      {lines.ticks.map(({ x, y }) => (
        <CrossTick key={`${x}-${y}`} x={x} y={y} />
      ))}
    </div>
  );
}
