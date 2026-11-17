import { describe, expect, test } from "vitest";

import { parseRunEvent } from "./schemas";

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
});
