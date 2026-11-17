import { describe, expect, test } from "vitest";

import { initialRunState, isActiveStatus, runReducer, type RunState } from "./reducer";
import type { RunEvent } from "./schemas";

const RUN_VIEW = { status: "queued", error: null, pending_interrupt: null } as const;

function play(events: readonly RunEvent[], start: RunState = initialRunState(RUN_VIEW)): RunState {
  return events.reduce(runReducer, start);
}

describe("initialRunState", () => {
  test("seeds status, error and the pending question from the run view", () => {
    const state = initialRunState({
      status: "awaiting_user",
      error: null,
      pending_interrupt: { type: "question", question: "Who is it for?" },
    });
    expect(state.status).toBe("awaiting_user");
    expect(state.interrupt).toEqual({ kind: "question", text: "Who is it for?" });
    expect(state.steps).toEqual([]);
  });

  test("reads a failed run's error and ignores a malformed one", () => {
    expect(
      initialRunState({ status: "failed", error: { code: "run.failed", message: "Boom" }, pending_interrupt: null })
        .error,
    ).toEqual({ code: "run.failed", message: "Boom" });
    expect(initialRunState({ status: "failed", error: { odd: true }, pending_interrupt: null }).error).toEqual({
      code: "run.failed",
      message: "The run failed.",
    });
  });
});

describe("runReducer", () => {
  test("adds a running step and marks it done", () => {
    const state = play([
      { type: "node_started", node: "interviewer" },
      { type: "node_finished", node: "interviewer" },
    ]);
    expect(state.steps).toEqual([{ node: "interviewer", done: true, tools: [] }]);
  });

  test("ignores a repeated start while the node's row is still running", () => {
    const state = play([
      { type: "node_started", node: "researcher" },
      { type: "node_started", node: "researcher" },
    ]);
    expect(state.steps).toHaveLength(1);
  });

  test("adds a second row when a finished node runs again", () => {
    const state = play([
      { type: "node_started", node: "scorer" },
      { type: "node_finished", node: "scorer" },
      { type: "node_started", node: "scorer" },
    ]);
    expect(state.steps.map((step) => step.done)).toEqual([true, false]);
  });

  test("a finish with no running row adds a done row", () => {
    expect(play([{ type: "node_finished", node: "planner" }]).steps).toEqual([
      { node: "planner", done: true, tools: [] },
    ]);
  });

  test("puts tool calls under the node's latest row, once per name", () => {
    const state = play([
      { type: "node_started", node: "researcher" },
      { type: "tool_call", node: "researcher", name: "web_search" },
      { type: "tool_call", node: "researcher", name: "web_search" },
      { type: "tool_call", node: "researcher", name: "fetch" },
    ]);
    expect(state.steps[0]?.tools).toEqual(["web_search", "fetch"]);
  });

  test("appends streamed text", () => {
    const state = play([
      { type: "token", node: "advisor", text: "Hello" },
      { type: "token", node: "advisor", text: " world" },
    ]);
    expect(state.text).toBe("Hello world");
  });

  test("records status, error and question", () => {
    const failed = play([
      { type: "run_status", status: "running" },
      { type: "run_status", status: "failed", error: { code: "run.failed", message: "Boom" } },
    ]);
    expect(failed.status).toBe("failed");
    expect(failed.error).toEqual({ code: "run.failed", message: "Boom" });

    const waiting = play([{ type: "interrupt", interrupt: { kind: "question", text: "Who pays?" } }]);
    expect(waiting.interrupt).toEqual({ kind: "question", text: "Who pays?" });
  });

  test("a status other than awaiting_user clears the question", () => {
    const state = play([
      { type: "interrupt", interrupt: { kind: "question", text: "Who pays?" } },
      { type: "run_status", status: "cancelled" },
    ]);
    expect(state.interrupt).toBeNull();
  });

  test("replaying the same events from a fresh state gives the same view", () => {
    const events: RunEvent[] = [
      { type: "run_status", status: "running" },
      { type: "node_started", node: "interviewer" },
      { type: "node_finished", node: "interviewer" },
      { type: "run_status", status: "succeeded" },
    ];
    expect(play(events)).toEqual(play(events));
  });

  test("never mutates the previous state", () => {
    const start = play([{ type: "node_started", node: "interviewer" }]);
    const snapshot = structuredClone(start);
    runReducer(start, { type: "node_finished", node: "interviewer" });
    runReducer(start, { type: "tool_call", node: "interviewer", name: "ask" });
    expect(start).toEqual(snapshot);
  });
});

describe("isActiveStatus", () => {
  test("queued, running and awaiting_user are active; terminal ones are not", () => {
    expect(["queued", "running", "awaiting_user"].every(isActiveStatus)).toBe(true);
    expect(["succeeded", "failed", "cancelled"].some(isActiveStatus)).toBe(false);
  });
});
