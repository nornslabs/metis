import { describe, expect, test } from "vitest";

import { UNREADABLE_PAUSE_CODE, parseRunEvent } from "./schemas";

const RUN_ID = "0196d6c4-0000-7000-8000-000000000001";

function frame(type: string, data: unknown): string {
  return JSON.stringify({ run_id: RUN_ID, type, data, ts: "2026-11-18T10:00:00Z" });
}

describe("parseRunEvent", () => {
  test("reads a node_started frame", () => {
    expect(parseRunEvent("node_started", frame("node_started", { node: "interviewer" }))).toEqual({
      type: "node_started",
      node: "interviewer",
    });
  });

  test("reads a failed run_status with its error", () => {
    const parsed = parseRunEvent(
      "run_status",
      frame("run_status", { status: "failed", error: { code: "run.failed", message: "Run failed" } }),
    );
    expect(parsed).toEqual({
      type: "run_status",
      status: "failed",
      error: { code: "run.failed", message: "Run failed" },
    });
  });

  test("reads a question interrupt", () => {
    const parsed = parseRunEvent(
      "interrupt",
      frame("interrupt", { type: "question", question: "Who pays?" }),
    );
    expect(parsed).toEqual({ type: "interrupt", interrupt: { kind: "question", text: "Who pays?" } });
  });

  test("keeps the details text of an approval interrupt", () => {
    const parsed = parseRunEvent(
      "interrupt",
      frame("interrupt", { type: "approval", action: "Export to Linear", details: "12 issues" }),
    );
    expect(parsed).toEqual({
      type: "interrupt",
      interrupt: { kind: "approval", text: "Export to Linear", details: "12 issues" },
    });
  });

  test("reads an approval interrupt as its action", () => {
    const parsed = parseRunEvent(
      "interrupt",
      frame("interrupt", { type: "approval", action: "Export to Linear", details: {} }),
    );
    expect(parsed).toEqual({
      type: "interrupt",
      interrupt: { kind: "approval", text: "Export to Linear" },
    });
  });

  test("reads token and tool_call frames", () => {
    expect(parseRunEvent("token", frame("token", { node: "scorer", text: "Hi" }))).toEqual({
      type: "token",
      node: "scorer",
      text: "Hi",
    });
    expect(parseRunEvent("tool_call", frame("tool_call", { node: "researcher", name: "search" }))).toEqual({
      type: "tool_call",
      node: "researcher",
      name: "search",
    });
  });

  test("reads a notice frame", () => {
    const data = { code: "research.skipped_no_exa", text: "Research is skipped: Exa isn't set up." };
    expect(parseRunEvent("notice", frame("notice", data))).toEqual({ type: "notice", ...data });
  });

  test("ignores a notice without text", () => {
    expect(parseRunEvent("notice", frame("notice", { code: "x" }))).toBeNull();
  });

  test("ignores unknown event names", () => {
    expect(parseRunEvent("score.param", frame("score.param", { name: "x" }))).toBeNull();
  });

  test("ignores frames that are not JSON or do not match the payload", () => {
    expect(parseRunEvent("node_started", "{not json")).toBeNull();
    expect(parseRunEvent("node_started", frame("node_started", { nope: 1 }))).toBeNull();
    expect(parseRunEvent("run_status", frame("run_status", { status: "exploded" }))).toBeNull();
  });

  test("ignores a frame whose envelope type differs from the event name", () => {
    expect(parseRunEvent("node_started", frame("node_finished", { node: "x" }))).toBeNull();
  });

  test("reads a score event", () => {
    const parsed = parseRunEvent("score", frame("score", { score_run_id: "s-1", total: 48, band: "advise" }));
    expect(parsed).toEqual({ type: "score", scoreRunId: "s-1", total: 48, band: "advise" });
  });

  test("ignores a score event with an unknown band", () => {
    expect(parseRunEvent("score", frame("score", { score_run_id: "s-1", total: 48, band: "great" }))).toBeNull();
  });

  test("reads an advice_decision interrupt", () => {
    const parsed = parseRunEvent(
      "interrupt",
      frame("interrupt", { type: "advice_decision", score_run_id: "s-1", total: 48, band: "advise", suggestion_ids: ["a"] }),
    );
    expect(parsed).toEqual({
      type: "interrupt",
      interrupt: { kind: "advice_decision", text: "s-1", scoreRunId: "s-1", total: 48, band: "advise" },
    });
  });

  test("reads a question with options, ids, a best fit and progress", () => {
    const parsed = parseRunEvent(
      "interrupt",
      frame("interrupt", {
        type: "question",
        question: "Who is it for?",
        multi: false,
        options: [
          { id: "o1", label: "Solo freelancers", detail: "One person.", recommended: true },
          { id: "o2", label: "Small agencies", recommended: false },
        ],
        allow_free_text: true,
        index: 2,
        total: 5,
      }),
    );
    expect(parsed).toEqual({
      type: "interrupt",
      interrupt: {
        kind: "question",
        text: "Who is it for?",
        multi: false,
        options: [
          { id: "o1", label: "Solo freelancers", detail: "One person.", recommended: true },
          { id: "o2", label: "Small agencies", recommended: false },
        ],
        allowFreeText: true,
        index: 2,
        total: 5,
      },
    });
  });

  test("reads a question the server sent with no options at all", () => {
    const parsed = parseRunEvent(
      "interrupt",
      frame("interrupt", { type: "question", question: "Why?", multi: false, options: [], allow_free_text: true, index: 1, total: 4 }),
    );
    expect(parsed).toEqual({
      type: "interrupt",
      interrupt: { kind: "question", text: "Why?", multi: false, options: [], allowFreeText: true, index: 1, total: 4 },
    });
  });

  test.each([
    ["an option without an id", { type: "question", question: "Q?", options: [{ label: "A" }] }],
    ["options that are not a list", { type: "question", question: "Q?", options: "A" }],
    ["an index of zero", { type: "question", question: "Q?", index: 0 }],
    ["a question without text", { type: "question", options: [] }],
  ])("turns an unreadable question (%s) into a notice, never an exception", (_name, payload) => {
    const parsed = parseRunEvent("interrupt", frame("interrupt", payload));
    expect(parsed).toMatchObject({ type: "notice", code: UNREADABLE_PAUSE_CODE });
  });

  test("reads a spec_review interrupt", () => {
    expect(
      parseRunEvent("interrupt", frame("interrupt", { type: "spec_review", spec_version_id: "sv1", number: 1, kind: "software" })),
    ).toEqual({
      type: "interrupt",
      interrupt: { kind: "spec_review", text: "sv1", specVersionId: "sv1", number: 1 },
    });
  });
});
