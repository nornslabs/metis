import { describe, expect, it } from "vitest";

import { planOf, task } from "./fixtures";
import { NODE_HEIGHT, NODE_WIDTH, layoutGraph } from "./graph";
import { buildPlanView } from "./view";

const layoutOf = (...args: Parameters<typeof planOf>) => layoutGraph(buildPlanView(planOf(...args)).tasks);

describe("layoutGraph", () => {
  it("is empty for no tasks", () => {
    expect(layoutGraph([])).toEqual({ width: 0, height: 0, nodes: [], edges: [] });
  });

  it("puts a long chain one task per rank, top to bottom", () => {
    const layout = layoutOf([[task("a", 1), task("b", 1, ["a"]), task("c", 1, ["b"])]]);
    const ys = layout.nodes.map((node) => node.y);
    expect(ys).toEqual([...ys].sort((left, right) => left - right));
    expect(new Set(ys).size).toBe(3);
    expect(layout.edges.map((edge) => `${edge.from}>${edge.to}`)).toEqual(["a>b", "b>c"]);
  });

  it("ranks a diamond by its longest chain and puts siblings side by side", () => {
    const layout = layoutOf([[task("a", 1), task("b", 1, ["a"]), task("c", 1, ["a"]), task("d", 1, ["b", "c"])]]);
    const at = (id: string) => layout.nodes.find((node) => node.view.task.id === id)!;
    expect(at("b").y).toBe(at("c").y);
    expect(at("b").x).not.toBe(at("c").x);
    expect(at("d").y).toBeGreaterThan(at("b").y);
    expect(layout.width).toBeGreaterThanOrEqual(2 * NODE_WIDTH);
    expect(layout.height).toBeGreaterThanOrEqual(3 * NODE_HEIGHT);
  });

  it("has a node for every task and an edge for every stored blocker", () => {
    const tasks = [task("a", 1), task("b", 2, ["a"]), task("c", 3, ["a", "b"])];
    const layout = layoutOf([tasks]);
    expect(layout.nodes).toHaveLength(3);
    expect(layout.edges).toHaveLength(3);
  });

  it("marks an edge critical only when both ends are on the critical path", () => {
    const layout = layoutOf([[task("a", 1), task("b", 1, ["a"]), task("c", 1, ["a"])]], ["a", "b"], 2);
    const critical = layout.edges.filter((edge) => edge.critical).map((edge) => `${edge.from}>${edge.to}`);
    expect(critical).toEqual(["a>b"]);
  });

  it("orders a rank by phase, then position, so the layout is stable", () => {
    const layout = layoutOf([[task("a", 1)], [task("b", 1)]]);
    expect(layout.nodes.map((node) => node.view.task.id)).toEqual(["a", "b"]);
  });

  it("ignores a blocker that is not in the plan and survives a cycle", () => {
    const layout = layoutOf([[task("a", 1, ["ghost"]), task("b", 1, ["c"]), task("c", 1, ["b"])]]);
    expect(layout.nodes).toHaveLength(3);
    expect(layout.edges.some((edge) => edge.from === "ghost")).toBe(false);
  });
});
