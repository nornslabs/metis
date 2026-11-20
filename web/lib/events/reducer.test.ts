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

describe("runReducer, scores", () => {
  test("remembers the newest score run the stream announced", () => {
    const state = play([
      { type: "score", scoreRunId: "s-1", total: 48, band: "advise" },
      { type: "score", scoreRunId: "s-2", total: 61, band: "promising" },
    ]);
    expect(state.scoreRunId).toBe("s-2");
  });

  test("seeds a pending advice decision from the run view", () => {
    const state = initialRunState({
      status: "awaiting_user",
      error: null,
      pending_interrupt: { type: "advice_decision", score_run_id: "s-1", total: 48, band: "advise", suggestion_ids: [] },
    });
    expect(state.interrupt).toMatchObject({ kind: "advice_decision", scoreRunId: "s-1", total: 48 });
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

describe("interruptCount", () => {
  const ask = (text: string): RunEvent => ({ type: "interrupt", interrupt: { kind: "question", text } });

  test("starts at zero, even with a seeded question", () => {
    expect(initialRunState(RUN_VIEW).interruptCount).toBe(0);
    const seeded = initialRunState({
      status: "awaiting_user",
      error: null,
      pending_interrupt: { type: "question", question: "Who?" },
    });
    expect(seeded.interruptCount).toBe(0);
  });

  test("counts every interrupt, so an identical question or a second approval is a new one", () => {
    const state = play([ask("Who?"), ask("Who?"), { type: "interrupt", interrupt: { kind: "approval", text: "Export" } }]);
    expect(state.interruptCount).toBe(3);
  });

  test("is not changed by other events", () => {
    const state = play([ask("Who?"), { type: "token", node: "interviewer", text: "hi" }, { type: "run_status", status: "running" }]);
    expect(state.interruptCount).toBe(1);
  });
});


describe("runReducer sync", () => {
  const question = { type: "question", question: "Who is it for?" } as const;
  const sync = (state: RunState, seed: Parameters<typeof initialRunState>[0]) =>
    runReducer(state, { type: "sync", seed });

  test("picks up a pause the stream never delivered", () => {
    const running = play([{ type: "run_status", status: "running" }]);
    const next = sync(running, { status: "awaiting_user", error: null, pending_interrupt: question });
    expect(next.status).toBe("awaiting_user");
    expect(next.interrupt).toEqual({ kind: "question", text: "Who is it for?" });
    expect(next.interruptCount).toBe(1);
  });

  test("returns the same state when the view shows nothing new", () => {
    const running = play([{ type: "run_status", status: "running" }]);
    expect(sync(running, { status: "running", error: null, pending_interrupt: null })).toBe(running);
  });

  test("does not count an interrupt the stream already delivered", () => {
    const paused = play([
      { type: "interrupt", interrupt: { kind: "question", text: "Who is it for?" } },
      { type: "run_status", status: "awaiting_user" },
    ]);
    expect(sync(paused, { status: "awaiting_user", error: null, pending_interrupt: question })).toBe(paused);
  });

  test("never moves a finished run back", () => {
    const done = play([{ type: "run_status", status: "succeeded" }]);
    expect(sync(done, { status: "running", error: null, pending_interrupt: null })).toBe(done);
  });

  test("picks up a failure with its error", () => {
    const running = play([{ type: "run_status", status: "running" }]);
    const next = sync(running, { status: "failed", error: { code: "run.failed", message: "Boom" }, pending_interrupt: null });
    expect(next.status).toBe("failed");
    expect(next.error).toEqual({ code: "run.failed", message: "Boom" });
  });

  test("keeps a notice once, even when the stream replays it", () => {
    const notice = { type: "notice", code: "research.skipped_no_exa", text: "Research is skipped." } as const;
    expect(play([notice, notice]).notices).toEqual([{ code: notice.code, text: notice.text }]);
  });

  test("marks the Researcher step skipped on research.skipped_no_exa", () => {
    const state = play([
      { type: "node_started", node: "researcher" },
      { type: "notice", code: "research.skipped_no_exa", text: "Research is skipped." },
    ]);
    expect(state.steps).toEqual([{ node: "researcher", done: true, skipped: true, tools: [] }]);
  });

  test("keeps one skipped row when node_finished follows the notice", () => {
    const state = play([
      { type: "node_started", node: "researcher" },
      { type: "notice", code: "research.skipped_no_exa", text: "Research is skipped." },
      { type: "node_finished", node: "researcher" },
    ]);
    expect(state.steps).toHaveLength(1);
    expect(state.steps[0]?.skipped).toBe(true);
  });

  test("a node_started after the skip notice does not add a running row", () => {
    const state = play([
      { type: "notice", code: "research.skipped_no_exa", text: "Research is skipped." },
      { type: "node_started", node: "researcher" },
    ]);
    expect(state.steps).toEqual([{ node: "researcher", done: true, skipped: true, tools: [] }]);
  });

  test("an unknown notice code leaves the steps alone", () => {
    const state = play([
      { type: "node_started", node: "researcher" },
      { type: "notice", code: "other.thing", text: "Heads up." },
    ]);
    expect(state.steps).toEqual([{ node: "researcher", done: false, tools: [] }]);
    expect(state.notices).toHaveLength(1);
  });

  test("closes a step still running when the run succeeds", () => {
    const state = play([
      { type: "node_started", node: "researcher" },
      { type: "run_status", status: "succeeded" },
    ]);
    expect(state.steps).toEqual([{ node: "researcher", done: true, tools: [] }]);
  });

  test("leaves a running step open when the run fails", () => {
    const state = play([
      { type: "node_started", node: "researcher" },
      { type: "run_status", status: "failed", error: { code: "run.failed", message: "Boom" } },
    ]);
    expect(state.steps[0]?.done).toBe(false);
  });
});
