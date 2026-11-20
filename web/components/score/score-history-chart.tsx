"use client";

import { useState, type CSSProperties } from "react";

import { cn } from "@/lib/cn";
import {
  BAND_LABELS,
  BUILD_FROM,
  MAX_TOTAL,
  PROMISING_FROM,
  chartPoints,
  formatDay,
  type ChartPoint,
  type ScoreRunSummary,
} from "@/lib/scores/view";

function pointSummary(point: ChartPoint): string {
  return `${point.total} / ${MAX_TOTAL} · ${BAND_LABELS[point.band]} · ${formatDay(point.createdAt)} · ${point.trigger}`;
}

/** Hairline across the chart at a total (`y` is a percentage from the top). */
function Threshold({ at }: { at: number }) {
  return (
    <line x1="0" x2="100" y1={MAX_TOTAL - at} y2={MAX_TOTAL - at} className="stroke-border" strokeWidth="1" vectorEffect="non-scaling-stroke" strokeDasharray="3 3" />
  );
}

/**
 * Totals over score runs, oldest first. The line is an SVG; each run is a focusable button over it
 * (so keyboard and screen-reader users reach every value) and the chosen run's details show below.
 */
export function ScoreHistoryChart({ history }: { history: readonly ScoreRunSummary[] }) {
  const points = chartPoints(history);
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = points.find((point) => point.id === activeId) ?? points.at(-1) ?? null;
  if (points.length < 2) return <p className="text-control text-muted-foreground">One score so far.</p>;
  const path = points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x} ${point.y}`).join(" ");
  return (
    <figure className="flex flex-col gap-1.5">
      <div role="group" aria-label="Score history" className="relative h-24 px-2 py-2">
        <div className="relative size-full">
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" className="absolute inset-0 size-full overflow-visible">
            <Threshold at={BUILD_FROM} />
            <Threshold at={PROMISING_FROM} />
            <path d={path} fill="none" className="stroke-foreground" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
          </svg>
          {points.map((point) => (
            <button
              key={point.id}
              type="button"
              aria-label={pointSummary(point)}
              aria-current={point.id === active?.id}
              onClick={() => setActiveId(point.id)}
              onMouseEnter={() => setActiveId(point.id)}
              onFocus={() => setActiveId(point.id)}
              style={{ "--x": `${point.x}%`, "--y": `${point.y}%` } as CSSProperties}
              className={cn(
                "absolute top-(--y) left-(--x) size-tick -translate-x-1/2 -translate-y-1/2 border border-foreground bg-background focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                point.id === active?.id && "bg-foreground",
              )}
            />
          ))}
        </div>
      </div>
      {active ? <figcaption className="text-meta text-muted-foreground">{pointSummary(active)}</figcaption> : null}
    </figure>
  );
}
