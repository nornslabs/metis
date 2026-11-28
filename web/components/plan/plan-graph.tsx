"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/cn";
import { NODE_HEIGHT, NODE_WIDTH, layoutGraph, type GraphNode } from "@/lib/plan/graph";
import type { PlanView } from "@/lib/plan/view";

const TITLE_MAX = 22;
/** Text positions inside a node: horizontal padding, and the baselines of the id row and the title row. */
const NODE_PAD_X = 10;
const ID_BASELINE = 16;
const TITLE_BASELINE = 33;
/** The arrow head at an edge's end: how far it sits above the node and how wide it is. */
const ARROW_GAP = 4;
const ARROW_SIZE = 6;
const ID_FONT_SIZE = 10;
const TITLE_FONT_SIZE = 11.5;

type ZoomMode = "fit" | "actual";

function truncated(title: string): string {
  return title.length > TITLE_MAX ? `${title.slice(0, TITLE_MAX - 1)}…` : title;
}

function edgePath(from: GraphNode, to: GraphNode): { curve: string; head: string } {
  const startX = from.x + NODE_WIDTH / 2;
  const startY = from.y + NODE_HEIGHT;
  const endX = to.x + NODE_WIDTH / 2;
  const endY = to.y;
  const middle = (startY + endY) / 2;
  return {
    curve: `M${startX},${startY} C${startX},${middle} ${endX},${middle} ${endX},${endY - ARROW_GAP}`,
    head: `M${endX - 3.5},${endY - ARROW_SIZE} L${endX},${endY - 1.5} L${endX + 3.5},${endY - ARROW_SIZE}`,
  };
}

interface PlanGraphProps {
  plan: PlanView;
  onOpenTask: (taskId: string) => void;
}

/** The tasks as a top-to-bottom dependency graph: nodes are the stored tasks, edges the stored blockers. */
export function PlanGraph({ plan, onOpenTask }: PlanGraphProps) {
  const layout = useMemo(() => layoutGraph(plan.tasks), [plan.tasks]);
  const nodesById = useMemo(() => new Map(layout.nodes.map((node) => [node.view.task.id, node])), [layout]);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState<number | null>(null);
  const [zoomMode, setZoomMode] = useState<ZoomMode>("fit");

  useEffect(() => {
    const element = containerRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const update = () => {
      // Subtract horizontal padding (px-3 = 24px) so the fitted SVG never triggers horizontal scroll.
      setContainerWidth(Math.max(0, element.clientWidth - 24));
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const canScale = containerWidth !== null && containerWidth > 0 && layout.width > containerWidth;
  const scale = zoomMode === "fit" && canScale ? containerWidth / layout.width : 1;
  const svgWidth = Math.round(layout.width * scale);
  const svgHeight = Math.round(layout.height * scale);

  return (
    <div className="flex flex-col">
      {canScale ? (
        <div className="flex items-center justify-between border-b bg-muted/20 px-4 py-1.5">
          <span className="text-meta text-muted-foreground">
            {zoomMode === "fit" ? `Scaled to fit (${Math.round(scale * 100)}%)` : "Actual size (100%)"}
          </span>
          <div role="group" aria-label="Graph zoom" className="inline-flex border bg-background">
            {(
              [
                ["fit", "Fit"],
                ["actual", "100%"],
              ] as const
            ).map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                aria-pressed={zoomMode === mode}
                onClick={() => setZoomMode(mode)}
                className={cn(
                  "h-5.5 px-2 text-meta not-first:border-l focus-visible:bg-accent focus-visible:outline-none",
                  zoomMode === mode
                    ? "bg-foreground text-background focus-visible:bg-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      <div ref={containerRef} className="overflow-auto px-3 pt-3 pb-5">
        <svg
          width={svgWidth}
          height={svgHeight}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          role="group"
          aria-label="Dependency graph"
          className="mx-auto block"
        >
          {layout.edges.map((edge) => {
            const from = nodesById.get(edge.from);
            const to = nodesById.get(edge.to);
            if (!from || !to) return null;
            const { curve, head } = edgePath(from, to);
            const className = edge.critical
              ? "fill-none stroke-foreground"
              : "fill-none stroke-muted-foreground/45";
            return (
              <g
                key={`${edge.from}:${edge.to}`}
                data-edge={`${from.view.code}>${to.view.code}`}
                data-critical={edge.critical ? "" : undefined}
              >
                <path d={curve} className={className} strokeWidth={edge.critical ? 1.6 : 1} />
                <path
                  d={head}
                  className={className}
                  strokeWidth={edge.critical ? 1.6 : 1}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </g>
            );
          })}
          {layout.nodes.map((node) => {
            const { view } = node;
            const open = () => onOpenTask(view.task.id);
            return (
              <g
                key={view.task.id}
                role="button"
                tabIndex={0}
                data-node={view.code}
                data-critical={view.critical ? "" : undefined}
                aria-label={`${view.code}: ${view.task.title}, ${view.task.estimate} points`}
                className="group cursor-pointer outline-none"
                onClick={open}
                onKeyDown={(event) => {
                  if (event.key !== "Enter" && event.key !== " ") return;
                  event.preventDefault();
                  open();
                }}
              >
                <title>{`${view.code} · ${view.task.title} · ${view.task.estimate} pts`}</title>
                <rect
                  x={node.x}
                  y={node.y}
                  width={NODE_WIDTH}
                  height={NODE_HEIGHT}
                  strokeWidth={view.critical ? 1.5 : 1}
                  className={`fill-card transition-colors group-hover:fill-accent group-hover:stroke-ring group-focus-visible:fill-accent group-focus-visible:stroke-ring ${view.critical ? "stroke-foreground" : "stroke-border"}`}
                />
                {view.critical ? (
                  <rect
                    x={node.x}
                    y={node.y}
                    width={2.5}
                    height={NODE_HEIGHT}
                    className="fill-foreground pointer-events-none"
                  />
                ) : null}
                <text
                  x={node.x + NODE_PAD_X}
                  y={node.y + ID_BASELINE}
                  fontSize={ID_FONT_SIZE}
                  fontWeight={500}
                  className="fill-muted-foreground font-mono"
                >
                  {`${view.code} · ${view.phaseCode}`}
                </text>
                <text
                  x={node.x + NODE_WIDTH - NODE_PAD_X}
                  y={node.y + ID_BASELINE}
                  fontSize={ID_FONT_SIZE}
                  fontWeight={500}
                  textAnchor="end"
                  className="fill-foreground font-mono"
                >
                  {view.task.estimate}
                </text>
                <text
                  x={node.x + NODE_PAD_X}
                  y={node.y + TITLE_BASELINE}
                  fontSize={TITLE_FONT_SIZE}
                  fontWeight={500}
                  className="fill-foreground"
                >
                  {truncated(view.task.title)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
