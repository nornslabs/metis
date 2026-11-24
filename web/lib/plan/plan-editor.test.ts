import { describe, expect, it, vi, type Mock } from "vitest";

import { ApiError } from "@/lib/api/errors";
import type { Plan, TaskPatch } from "@/lib/schemas/plan";

import { planOf, task } from "./fixtures";
import { PlanEditor, type PlanEditorPorts } from "./plan-editor";

const apiError = (code: string, status = 409) => new ApiError({ status, code, title: code });
const withVersion = (plan: Plan, version: number): Plan => ({ ...plan, version });

type MockPorts = { [Name in keyof PlanEditorPorts]: Mock<PlanEditorPorts[Name]> };

function setup(overrides: Partial<MockPorts> = {}) {
  let plan = planOf([[task("a", 2), task("b", 3)]]);
  const ports: MockPorts = {
    current: vi.fn(() => plan),
    save: vi.fn(async (_planId: string, _taskId: string, version: number) => withVersion(plan, version + 1)),
    refresh: vi.fn(async () => withVersion(plan, 9)),
    publish: vi.fn((next: Plan | null) => {
      if (next) plan = next;
    }),
    ...overrides,
  };
  return { editor: new PlanEditor(ports), ports };
}

describe("PlanEditor", () => {
  it("saves a change on the plan's version and publishes the answer", async () => {
    const { editor, ports } = setup();
    editor.edit("a", { estimate: 5 });
    await vi.waitFor(() => expect(editor.getState().status).toBe("idle"));
    expect(ports.save).toHaveBeenCalledWith("plan1", "a", 1, { estimate: 5 });
    expect(ports.publish).toHaveBeenCalledTimes(1);
    expect(editor.getState().saved).toBe(1);
  });

  it("sends changes made during a save afterwards, on the version the save returned", async () => {
    let release: () => void = () => undefined;
    const { editor, ports } = setup({
      save: vi.fn(
        (_planId: string, _taskId: string, version: number) =>
          new Promise<Plan>((resolve) => {
            release = () => resolve(withVersion(planOf([[task("a", 2), task("b", 3)]]), version + 1));
          }),
      ),
    });
    editor.edit("a", { estimate: 5 });
    editor.edit("b", { title: "Renamed" });
    expect(ports.save).toHaveBeenCalledTimes(1);
    release();
    await vi.waitFor(() => expect(ports.save).toHaveBeenCalledTimes(2));
    expect(ports.save).toHaveBeenLastCalledWith("plan1", "b", 2, { title: "Renamed" });
    release();
    await vi.waitFor(() => expect(editor.getState().status).toBe("idle"));
  });

  it("merges two changes to the same task into one request", async () => {
    let release: () => void = () => undefined;
    const sent: TaskPatch[] = [];
    const { editor } = setup({
      save: vi.fn(
        (_planId: string, _taskId: string, version: number, patch: TaskPatch) =>
          new Promise<Plan>((resolve) => {
            sent.push(patch);
            release = () => resolve(withVersion(planOf([[task("a", 2)]]), version + 1));
          }),
      ),
    });
    editor.edit("a", { estimate: 5 });
    editor.edit("b", { estimate: 1 });
    editor.edit("b", { title: "T" });
    release();
    await vi.waitFor(() => expect(sent).toHaveLength(2));
    expect(sent[1]).toEqual({ estimate: 1, title: "T" });
    release();
    await vi.waitFor(() => expect(editor.getState().status).toBe("idle"));
  });

  it("pauses on a stale version until Reload, then takes the server's plan", async () => {
    const { editor, ports } = setup({
      save: vi.fn(async () => {
        throw apiError("plan.conflict");
      }),
    });
    editor.edit("a", { estimate: 5 });
    await vi.waitFor(() => expect(editor.getState().status).toBe("conflict"));
    editor.edit("a", { estimate: 8 });
    expect(ports.save).toHaveBeenCalledTimes(1);
    await editor.reload();
    expect(ports.refresh).toHaveBeenCalledTimes(1);
    expect(ports.publish).toHaveBeenLastCalledWith(expect.objectContaining({ version: 9 }));
    expect(editor.getState().status).toBe("idle");
  });

  it("keeps a failed change for Retry", async () => {
    const save = vi
      .fn<PlanEditorPorts["save"]>()
      .mockRejectedValueOnce(new Error("offline"))
      .mockImplementation(async (_planId, _taskId, version) => withVersion(planOf([[task("a", 2)]]), version + 1));
    const { editor } = setup({ save });
    editor.edit("a", { estimate: 5 });
    await vi.waitFor(() => expect(editor.getState().status).toBe("failed"));
    expect(editor.getState().error).not.toBeNull();
    await editor.flush();
    expect(save).toHaveBeenCalledTimes(2);
    expect(editor.getState().status).toBe("idle");
  });

  it("refetches the plan when it was fixed (ready) in the meantime", async () => {
    const { editor, ports } = setup({
      save: vi.fn(async () => {
        throw apiError("plan.invalid_transition");
      }),
    });
    editor.edit("a", { estimate: 5 });
    await vi.waitFor(() => expect(ports.refresh).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => expect(editor.getState().status).toBe("idle"));
    expect(ports.publish).toHaveBeenCalled();
  });

  it("sends a second change to the same task made during its save", async () => {
    let release: () => void = () => undefined;
    const sent: TaskPatch[] = [];
    const { editor } = setup({
      save: vi.fn(
        (_planId: string, _taskId: string, version: number, patch: TaskPatch) =>
          new Promise<Plan>((resolve) => {
            sent.push(patch);
            release = () => resolve(withVersion(planOf([[task("a", 2)]]), version + 1));
          }),
      ),
    });
    editor.edit("a", { estimate: 5 });
    editor.edit("a", { title: "New" });
    release();
    await vi.waitFor(() => expect(sent).toHaveLength(2));
    expect(sent[1]).toEqual({ estimate: 5, title: "New" });
    release();
    await vi.waitFor(() => expect(editor.getState().status).toBe("idle"));
  });
});
