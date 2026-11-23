import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { ApiError } from "@/lib/api/errors";
import type { SpecOverview, SpecVersion } from "@/lib/schemas/spec";

import { AUTOSAVE_DELAY_MS, SpecEditor, currentMarkdown, isLocked, type SpecEditorPorts } from "./spec-editor";

const md = (problem: string) => `## Problem\n\n${problem}\n\n## Target users\n\nSolo founders.\n`;
const version = (number: number, problem: string, source: SpecVersion["source"] = "agent"): SpecVersion => ({
  id: `v${number}`,
  idea_id: "i",
  number,
  source,
  content_md: md(problem),
  sections: {},
  run_id: null,
  created_by: null,
  created_at: "2026-11-23T10:00:00Z",
});
const apiError = (code: string, status = 409) => new ApiError({ status, code, title: code });

type MockPorts = { [Name in keyof SpecEditorPorts]: Mock<SpecEditorPorts[Name]> };

function setup(overrides: Partial<MockPorts> = {}) {
  const ports: MockPorts = {
    save: vi.fn(async (base: number, text: string) => ({ ...version(base + 1, "", "user"), content_md: text })),
    confirm: vi.fn(async (number: number) => ({ confirmed: version(number, "x"), run_id: "r1" })),
    refresh: vi.fn(async (): Promise<SpecOverview> => ({ latest: version(5, "elsewhere"), confirmed: null })),
    publish: vi.fn(),
    ...overrides,
  };
  const editor = new SpecEditor(ports);
  editor.sync({ latest: version(1, "draft"), confirmed: null });
  return { editor, ports };
}

describe("SpecEditor autosave", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("saves once, 700ms after the last change, on the newest version", async () => {
    const { editor, ports } = setup();
    editor.edit("problem", "a");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS - 100);
    editor.edit("problem", "ab");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS - 100);
    expect(ports.save).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(200);
    expect(ports.save).toHaveBeenCalledTimes(1);
    expect(ports.save).toHaveBeenCalledWith(1, md("ab"));
    expect(editor.getState().latest?.number).toBe(2);
    expect(editor.getState().draftMd).toBeNull();
    expect(editor.getState().status).toBe("idle");
    expect(ports.publish).toHaveBeenCalledTimes(1);
  });

  it("saves edits made during a save right after it, on the version it returned", async () => {
    let release: () => void = () => undefined;
    const save: Mock<SpecEditorPorts["save"]> = vi.fn(
      (base: number, text: string) =>
        new Promise<SpecVersion>((resolve) => {
          release = () => resolve({ ...version(base + 1, "", "user"), content_md: text });
        }),
    );
    const { editor } = setup({ save });
    editor.edit("problem", "one");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS);
    expect(editor.getState().status).toBe("saving");
    editor.edit("problem", "two");
    expect(editor.getState().status).toBe("saving");
    release();
    await vi.advanceTimersByTimeAsync(0);
    // The save loop picks the second edit up at once, on the version the first save returned.
    expect(save).toHaveBeenCalledTimes(2);
    release();
    await vi.advanceTimersByTimeAsync(0);
    expect(save).toHaveBeenNthCalledWith(1, 1, md("one"));
    expect(save).toHaveBeenNthCalledWith(2, 2, md("two"));
    expect(editor.getState().latest?.number).toBe(3);
  });

  it("saves nothing when the text did not change", async () => {
    const { editor, ports } = setup();
    editor.edit("problem", "draft");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS * 2);
    expect(ports.save).not.toHaveBeenCalled();
    expect(editor.getState().status).toBe("idle");
  });

  it("keeps the typed text when a save fails, and a retry saves it", async () => {
    const { editor, ports } = setup();
    ports.save.mockRejectedValueOnce(apiError("common.unexpected", 500));
    editor.edit("problem", "typed");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS);
    expect(editor.getState().status).toBe("failed");
    expect(currentMarkdown(editor.getState())).toBe(md("typed"));
    expect(await editor.flush()).toBe(true);
    expect(editor.getState().latest?.number).toBe(2);
  });

  it("pauses on a conflict and shows the newest version after a reload", async () => {
    const { editor, ports } = setup();
    ports.save.mockRejectedValueOnce(apiError("spec.conflict"));
    editor.edit("problem", "mine");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS);
    expect(editor.getState().status).toBe("conflict");
    editor.edit("problem", "more");
    expect(editor.getState().draftMd).toBe(md("mine"));
    const before = editor.getState().epoch;
    await editor.reload();
    expect(editor.getState().status).toBe("idle");
    expect(editor.getState().latest?.number).toBe(5);
    expect(editor.getState().draftMd).toBeNull();
    expect(editor.getState().epoch).toBe(before + 1);
  });

  it("shows the server's version, locked, when the spec was confirmed elsewhere", async () => {
    const confirmed = version(2, "final");
    const { editor, ports } = setup({ refresh: vi.fn(async (): Promise<SpecOverview> => ({ latest: confirmed, confirmed })) });
    ports.save.mockRejectedValueOnce(apiError("spec.invalid_transition"));
    editor.edit("problem", "late");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS);
    expect(isLocked(editor.getState())).toBe(true);
  });

  it("ignores edits once the spec is locked", () => {
    const { editor } = setup();
    const confirmed = version(1, "draft");
    editor.sync({ latest: confirmed, confirmed });
    editor.edit("problem", "nope");
    expect(editor.getState().draftMd).toBeNull();
  });
});

describe("SpecEditor sync", () => {
  it("does not replace what is being typed with a newer server version", () => {
    const { editor } = setup();
    editor.edit("problem", "typing");
    editor.sync({ latest: version(2, "other"), confirmed: null });
    expect(editor.getState().latest?.number).toBe(1);
    expect(editor.getState().draftMd).toBe(md("typing"));
  });

  it("takes a newer version when nothing is being typed", () => {
    const { editor } = setup();
    const epoch = editor.getState().epoch;
    editor.sync({ latest: version(2, "other"), confirmed: null });
    expect(editor.getState().latest?.number).toBe(2);
    expect(editor.getState().epoch).toBe(epoch + 1);
  });
});

describe("SpecEditor confirm", () => {
  it("saves the pending edit first, then confirms that version", async () => {
    const { editor, ports } = setup();
    editor.edit("problem", "last");
    await editor.confirm();
    expect(ports.save).toHaveBeenCalledWith(1, md("last"));
    expect(ports.confirm).toHaveBeenCalledWith(2);
    expect(isLocked(editor.getState())).toBe(true);
  });

  it("does not confirm while a save is in conflict", async () => {
    const { editor, ports } = setup();
    ports.save.mockRejectedValueOnce(apiError("spec.conflict"));
    editor.edit("problem", "mine");
    await editor.confirm();
    expect(ports.confirm).not.toHaveBeenCalled();
    expect(editor.getState().status).toBe("conflict");
    expect(editor.getState().confirming).toBe(false);
  });

  it("shows the confirmed spec with a way to continue when the run could not be enqueued", async () => {
    const confirmed = version(1, "draft");
    const { editor, ports } = setup({ refresh: vi.fn(async (): Promise<SpecOverview> => ({ latest: confirmed, confirmed })) });
    ports.confirm.mockRejectedValueOnce(apiError("run.enqueue_failed", 503));
    await editor.confirm();
    expect(isLocked(editor.getState())).toBe(true);
    expect(editor.getState().confirmProblem).toBe("enqueue");
    await editor.confirm();
    expect(ports.confirm).toHaveBeenCalledTimes(2);
    expect(editor.getState().confirmProblem).toBeNull();
  });
});

describe("SpecEditor versions", () => {
  it("saves typed text before it shows an older version", async () => {
    const { editor, ports } = setup();
    editor.edit("problem", "Typed");
    await editor.showVersion(1);

    expect(ports.save).toHaveBeenCalledTimes(1);
    expect(editor.getState().view).toEqual({ mode: "version", number: 1 });
    expect(editor.getState().draftMd).toBeNull();
  });

  it("shows compare, and going back restarts the fields from the newest text", async () => {
    const { editor } = setup();
    await editor.showCompare(1);
    expect(editor.getState().view).toEqual({ mode: "compare", from: 1 });

    const epoch = editor.getState().epoch;
    editor.showEdit();
    expect(editor.getState().view).toEqual({ mode: "edit" });
    expect(editor.getState().epoch).toBe(epoch + 1);
  });

  it("restores an older text as a new version on the newest number", async () => {
    const { editor, ports } = setup();
    await editor.restore(md("Old text"));

    expect(ports.save).toHaveBeenCalledWith(1, md("Old text"));
    expect(editor.getState().latest?.number).toBe(2);
    expect(editor.getState().view).toEqual({ mode: "edit" });
  });

  it("does not restore the text it already has", async () => {
    const { editor, ports } = setup();
    await editor.restore(md("draft"));
    expect(ports.save).not.toHaveBeenCalled();
  });

  it("does not restore into a locked spec", async () => {
    const { editor, ports } = setup();
    editor.sync({ latest: version(1, "draft"), confirmed: version(1, "draft") });
    await editor.restore(md("Old text"));
    expect(ports.save).not.toHaveBeenCalled();
  });
});

describe("SpecEditor versions when a save fails", () => {
  it("stays on the draft when the pending save conflicts", async () => {
    const { editor } = setup({ save: vi.fn(async () => Promise.reject(apiError("spec.conflict"))) });
    editor.edit("problem", "Typed");
    await editor.showVersion(1);
    expect(editor.getState().view).toEqual({ mode: "edit" });
    expect(editor.getState().status).toBe("conflict");
  });

  it("does nothing when going back to edit from edit", () => {
    const { editor } = setup();
    const epoch = editor.getState().epoch;
    editor.showEdit();
    expect(editor.getState().epoch).toBe(epoch);
  });
});
