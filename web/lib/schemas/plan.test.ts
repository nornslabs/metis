import { describe, expect, it } from "vitest";

import { planOf, task } from "@/lib/plan/fixtures";

import { planSchema, reviewedPhaseSchema, taskTitleSchema } from "./plan";

describe("planSchema", () => {
  it("reads the server's plan with its phases, tasks and critical path", () => {
    const plan = planOf([[task("a", 2), task("b", 3, ["a"])]], ["a", "b"], 5);
    expect(planSchema.parse(plan)).toEqual(plan);
  });

  it("refuses a plan without its critical path or with a bad status", () => {
    const plan = planOf([[task("a", 2)]]);
    expect(planSchema.safeParse({ ...plan, critical_path: undefined }).success).toBe(false);
    expect(planSchema.safeParse({ ...plan, status: "done" }).success).toBe(false);
  });

  it("refuses a task whose blockers are not a list", () => {
    const plan = planOf([[task("a", 2)]]);
    const broken = { ...plan, phases: [{ ...plan.phases[0], tasks: [{ ...plan.phases[0]!.tasks[0], blocked_by: "t1" }] }] };
    expect(planSchema.safeParse(broken).success).toBe(false);
  });
});

describe("reviewedPhaseSchema and taskTitleSchema", () => {
  it("needs all three phase fields", () => {
    expect(reviewedPhaseSchema.safeParse({ name: "a", goal: "b" }).success).toBe(false);
  });

  it("trims a title and refuses an empty or long one", () => {
    expect(taskTitleSchema.parse("  Set up CI ")).toBe("Set up CI");
    expect(taskTitleSchema.safeParse("   ").success).toBe(false);
    expect(taskTitleSchema.safeParse("x".repeat(201)).success).toBe(false);
  });
});
