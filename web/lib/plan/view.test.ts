import { describe, expect, it } from "vitest";

import { planOf, task } from "./fixtures";
import { buildPlanView } from "./view";

describe("buildPlanView", () => {
  const plan = planOf([[task("a", 2), task("b", 3, ["a"])], [task("c", 5, ["b"])]], ["a", "b", "c"], 10);

  it("numbers tasks in plan order and phases from one", () => {
    const view = buildPlanView(plan);
    expect(view.tasks.map((entry) => entry.code)).toEqual(["T1", "T2", "T3"]);
    expect(view.tasks.map((entry) => entry.phaseCode)).toEqual(["P1", "P1", "P2"]);
    expect(view.byId.get("c")?.code).toBe("T3");
  });

  it("totals points per phase and in the summary", () => {
    const view = buildPlanView(plan);
    expect(view.phases.map((phase) => phase.points)).toEqual([5, 5]);
    expect(view.summary).toEqual({ phases: 2, tasks: 3, points: 10, criticalPoints: 10, criticalTasks: 3 });
  });

  it("marks only the tasks on the server's critical path", () => {
    const view = buildPlanView(planOf([[task("a", 2), task("b", 3)]], ["b"], 3));
    expect(view.tasks.map((entry) => entry.critical)).toEqual([false, true]);
  });

  it("does not change the plan it reads", () => {
    const before = JSON.stringify(plan);
    buildPlanView(plan);
    expect(JSON.stringify(plan)).toBe(before);
  });
});
