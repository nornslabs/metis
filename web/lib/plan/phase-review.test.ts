import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";

import { PhaseReview } from "./phase-review";

const proposal = [
  { name: "Foundations", goal: "Set up", exit_criteria: "Builds" },
  { name: "MVP", goal: "Ship", exit_criteria: "Users" },
];

function setup(resume = vi.fn(async () => undefined)) {
  const review = new PhaseReview({ resume });
  review.sync("run1", proposal);
  return { review, resume };
}

describe("PhaseReview", () => {
  it("starts from the proposal, not edited", () => {
    const { review } = setup();
    expect(review.getState().phases.map((phase) => phase.name)).toEqual(["Foundations", "MVP"]);
    expect(review.edited()).toBe(false);
    expect(review.blockedReason()).toBeNull();
  });

  it("sends the proposal itself when nothing changed", async () => {
    const { review, resume } = setup();
    await review.approve();
    expect(resume).toHaveBeenCalledWith("run1", proposal);
    expect(review.getState().status).toBe("sent");
  });

  it("sends exactly the edited list", async () => {
    const { review, resume } = setup();
    const [first, second] = review.getState().phases;
    review.edit(first!.key, "name", "Base");
    review.move(second!.key, -1);
    review.add();
    const added = review.getState().phases.at(-1)!;
    review.edit(added.key, "name", "Launch");
    review.edit(added.key, "goal", "Go live");
    review.edit(added.key, "exit_criteria", "Live");
    expect(review.edited()).toBe(true);
    await review.approve();
    expect(resume).toHaveBeenCalledWith("run1", [
      { name: "MVP", goal: "Ship", exit_criteria: "Users" },
      { name: "Base", goal: "Set up", exit_criteria: "Builds" },
      { name: "Launch", goal: "Go live", exit_criteria: "Live" },
    ]);
  });

  it("blocks Approve with the reason while a phase is incomplete", async () => {
    const { review, resume } = setup();
    review.add();
    expect(review.blockedReason()).toBe("P3 needs a name.");
    await review.approve();
    expect(resume).not.toHaveBeenCalled();
  });

  it("keeps every edit when the server refuses the list", async () => {
    const resume = vi.fn(async () => {
      throw new ApiError({ status: 422, code: "run.invalid_resume", title: "Invalid", detail: "Too many phases." });
    });
    const { review } = setup(resume);
    review.edit(review.getState().phases[0]!.key, "name", "Base");
    await review.approve();
    expect(review.getState().status).toBe("failed");
    expect(review.getState().error).toBe("Too many phases.");
    expect(review.getState().phases[0]!.name).toBe("Base");
    await review.approve();
    expect(resume).toHaveBeenCalledTimes(2);
  });

  it("is read-only once sent and sends only once", async () => {
    const { review, resume } = setup();
    await review.approve();
    review.edit(review.getState().phases[0]!.key, "name", "Late");
    await review.approve();
    expect(review.getState().phases[0]!.name).toBe("Foundations");
    expect(resume).toHaveBeenCalledTimes(1);
  });

  it("starts over for a new proposal but keeps edits for the same one", () => {
    const { review } = setup();
    review.edit(review.getState().phases[0]!.key, "name", "Base");
    review.sync("run1", proposal);
    expect(review.getState().phases[0]!.name).toBe("Base");
    review.sync("run2", [proposal[1]!]);
    expect(review.getState().phases).toHaveLength(1);
    expect(review.getState().status).toBe("idle");
  });
});
