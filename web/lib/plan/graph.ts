import type { TaskView } from "@/lib/plan/view";

export const NODE_WIDTH = 160;
export const NODE_HEIGHT = 44;
const GAP_X = 14;
const GAP_Y = 30;
const PADDING = 12;

export interface GraphNode {
  readonly view: TaskView;
  readonly x: number;
  readonly y: number;
}

export interface GraphEdge {
  readonly from: string;
  readonly to: string;
  /** Both ends are on the critical path. */
  readonly critical: boolean;
}

export interface GraphLayout {
  readonly width: number;
  readonly height: number;
  readonly nodes: readonly GraphNode[];
  readonly edges: readonly GraphEdge[];
}

/** Rank = the longest chain of blockers above a task (0 for a task nothing blocks it). */
function rankTasks(tasks: readonly TaskView[]): ReadonlyMap<string, number> {
  const byId = new Map(tasks.map((view) => [view.task.id, view]));
  const ranks = new Map<string, number>();
  const visiting = new Set<string>();
  const rankOf = (id: string): number => {
    const known = ranks.get(id);
    if (known !== undefined) return known;
    // A cycle cannot be stored (the server refuses it); the guard keeps a bad payload from looping.
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const blockers = (byId.get(id)?.task.blocked_by ?? []).filter((blocker) => byId.has(blocker));
    const rank = blockers.length === 0 ? 0 : 1 + Math.max(...blockers.map(rankOf));
    visiting.delete(id);
    ranks.set(id, rank);
    return rank;
  };
  for (const view of tasks) rankOf(view.task.id);
  return ranks;
}

/**
 * Lays the tasks out top to bottom by dependency rank. Inside a rank tasks are ordered by phase,
 * then position, so the layout is stable. Edges are exactly the stored `blocked_by` pairs.
 */
export function layoutGraph(tasks: readonly TaskView[]): GraphLayout {
  if (tasks.length === 0) return { width: 0, height: 0, nodes: [], edges: [] };
  const ranks = rankTasks(tasks);
  const rows = new Map<number, TaskView[]>();
  for (const view of tasks) {
    const rank = ranks.get(view.task.id) ?? 0;
    rows.set(rank, [...(rows.get(rank) ?? []), view]);
  }
  const rankOrder = [...rows.keys()].sort((a, b) => a - b);
  const widest = Math.max(...[...rows.values()].map((row) => row.length));
  const width = widest * NODE_WIDTH + (widest - 1) * GAP_X + PADDING * 2;
  const height = rankOrder.length * NODE_HEIGHT + (rankOrder.length - 1) * GAP_Y + PADDING * 2;

  const nodes: GraphNode[] = rankOrder.flatMap((rank, rowIndex) => {
    const row = [...(rows.get(rank) ?? [])].sort(
      (a, b) => a.phaseIndex - b.phaseIndex || a.task.position - b.task.position,
    );
    const rowWidth = row.length * NODE_WIDTH + (row.length - 1) * GAP_X;
    return row.map((view, column) => ({
      view,
      x: (width - rowWidth) / 2 + column * (NODE_WIDTH + GAP_X),
      y: PADDING + rowIndex * (NODE_HEIGHT + GAP_Y),
    }));
  });

  const known = new Map(tasks.map((view) => [view.task.id, view]));
  const edges: GraphEdge[] = tasks.flatMap((view) =>
    view.task.blocked_by
      .filter((blocker) => known.has(blocker))
      .map((blocker) => ({
        from: blocker,
        to: view.task.id,
        critical: view.critical && (known.get(blocker)?.critical ?? false),
      })),
  );
  return { width, height, nodes, edges };
}
