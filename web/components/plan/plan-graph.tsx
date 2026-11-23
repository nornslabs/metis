"use client";

import { useMemo } from "react";

import { NODE_HEIGHT, NODE_WIDTH, layoutGraph, type GraphNode } from "@/lib/plan/graph";
import type { PlanView } from "@/lib/plan/view";

const TITLE_MAX = 22;
/** Text positions inside a node: left padding, and the baselines of the id row and the title row. */
const NODE_PAD_X = 8;
const ID_BASELINE = 15;
const TITLE_BASELINE = 31;
/** The arrow head at an edge's end: how far it sits above the node and how wide it is. */
const ARROW_GAP = 3;
const ARROW_SIZE = 5;
const ID_FONT_SIZE = 10;
const TITLE_FONT_SIZE = 11.5;

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
    head: `M${endX - ARROW_GAP},${endY - ARROW_SIZE} L${endX},${endY - 1} L${endX + ARROW_GAP},${endY - ARROW_SIZE}`,
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
  return (
    <div className="grid justify-center overflow-auto px-2 pt-3 pb-4">
      <svg width={layout.width} height={layout.height} viewBox={`0 0 ${layout.width} ${layout.height}`} role="group" aria-label="Dependency graph" className="block">
        {layout.edges.map((edge) => {
          const from = nodesById.get(edge.from);
          const to = nodesById.get(edge.to);
          if (!from || !to) return null;
          const { curve, head } = edgePath(from, to);
          const className = edge.critical ? "fill-none stroke-foreground" : "fill-none stroke-ring opacity-70";
          return (
            <g key={`${edge.from}:${edge.to}`} data-edge={`${from.view.code}>${to.view.code}`} data-critical={edge.critical ? "" : undefined}>
              <path d={curve} className={className} strokeWidth={edge.critical ? 1.5 : 1} />
              <path d={head} className={className} strokeWidth={edge.critical ? 1.5 : 1} />
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
                className={`fill-background transition-colors group-hover:fill-accent group-hover:stroke-ring group-focus-visible:fill-accent group-focus-visible:stroke-ring ${view.critical ? "stroke-foreground" : "stroke-border"}`}
              />
              <text x={node.x + NODE_PAD_X} y={node.y + ID_BASELINE} fontSize={ID_FONT_SIZE} fontWeight={500} className="fill-muted-foreground font-mono">
                {`${view.code} · ${view.phaseCode}`}
              </text>
              <text x={node.x + NODE_WIDTH - NODE_PAD_X} y={node.y + ID_BASELINE} fontSize={ID_FONT_SIZE} fontWeight={500} textAnchor="end" className="fill-foreground font-mono">
                {view.task.estimate}
              </text>
              <text x={node.x + NODE_PAD_X} y={node.y + TITLE_BASELINE} fontSize={TITLE_FONT_SIZE} fontWeight={500} className="fill-foreground">
                {truncated(view.task.title)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
