import { describe, expect, it } from "vitest";

import { PHASE_LIMITS } from "@/lib/schemas/plan";

import { addPhase, isEdited, movePhase, phasesProblem, removePhase, renamePhase, toDraft, toReviewed } from "./phases";

const proposal = [
  { name: "Foundations", goal: "Set up", exit_criteria: "Builds" },
  { name: "MVP", goal: "Ship", exit_criteria: "Users" },
];

describe("phase edits", () => {
  it("renames one field of one phase without touching the input", () => {
    const phases = toDraft(proposal);
    const key = phases[0]!.key;
    const next = renamePhase(phases, key, "name", "Base");
    expect(next[0]!.name).toBe("Base");
    expect(next[1]).toBe(phases[1]);
    expect(phases[0]!.name).toBe("Foundations");
  });

  it("moves a phase and keeps it in place at the ends", () => {
    const phases = toDraft(proposal);
    const [first, second] = [phases[0]!.key, phases[1]!.key];
    expect(movePhase(phases, first, 1).map((phase) => phase.key)).toEqual([second, first]);
    expect(movePhase(phases, first, -1)).toBe(phases);
    expect(movePhase(phases, second, 1)).toBe(phases);
  });

  it("adds an empty phase at the end and stops at the limit", () => {
    const phases = toDraft(proposal);
    const added = addPhase(phases);
    expect(added).toHaveLength(3);
    expect(added[2]).toMatchObject({ name: "", goal: "", exit_criteria: "" });
    const full = Array.from({ length: PHASE_LIMITS.maxPhases }, () => proposal[0]!);
    expect(addPhase(toDraft(full))).toHaveLength(PHASE_LIMITS.maxPhases);
  });

  it("removes a phase but never the last one", () => {
    const phases = toDraft(proposal);
    const removed = removePhase(phases, phases[0]!.key);
    expect(removed.map((phase) => phase.name)).toEqual(["MVP"]);
    expect(removePhase(removed, removed[0]!.key)).toBe(removed);
  });

  it("sends the phases without keys and with trimmed text", () => {
    const phases = renamePhase(toDraft(proposal), toDraft(proposal)[0]!.key, "name", " x ");
    expect(toReviewed(toDraft([{ name: " a ", goal: "g ", exit_criteria: " e" }]))).toEqual([{ name: "a", goal: "g", exit_criteria: "e" }]);
    expect(phases).toHaveLength(2);
  });
});

describe("phasesProblem", () => {
  it("accepts the proposal", () => {
    expect(phasesProblem(toDraft(proposal))).toBeNull();
  });

  it("names the phase and the missing field", () => {
    const empty = toDraft([proposal[0]!, { name: "Next", goal: "", exit_criteria: "x" }]);
    expect(phasesProblem(empty)).toBe("P2 needs a goal.");
    expect(phasesProblem(toDraft([{ name: " ", goal: "g", exit_criteria: "e" }]))).toBe("P1 needs a name.");
    expect(phasesProblem(toDraft([{ name: "n", goal: "g", exit_criteria: "" }]))).toBe('P1 needs a "Done when".');
  });

  it("refuses text over the limits and an empty list", () => {
    expect(phasesProblem(toDraft([{ name: "n".repeat(PHASE_LIMITS.name + 1), goal: "g", exit_criteria: "e" }]))).toContain("name");
    expect(phasesProblem(toDraft([{ name: "n", goal: "g".repeat(PHASE_LIMITS.text + 1), exit_criteria: "e" }]))).toContain("over");
    expect(phasesProblem([])).toBe("Add at least one phase.");
  });
});

describe("isEdited", () => {
  it("is false for the proposal and true after any change", () => {
    const phases = toDraft(proposal);
    expect(isEdited(phases, proposal)).toBe(false);
    expect(isEdited(renamePhase(phases, phases[0]!.key, "goal", "Other"), proposal)).toBe(true);
    expect(isEdited(movePhase(phases, phases[0]!.key, 1), proposal)).toBe(true);
    expect(isEdited(removePhase(phases, phases[0]!.key), proposal)).toBe(true);
  });
});
