import { describe, expect, test } from "vitest";

import type { ExportSummary } from "@/lib/schemas/export";

import { exportStatusView, progressLine, progressPercent, type LiveExport } from "./status";

const PROGRESS = { item: "issue", name: "Build the API", action: "create", done: 3, total: 12 } as const;

function live(over: Partial<LiveExport>): LiveExport {
  return { runId: "r1", status: "running", progress: null, finish: null, error: null, ...over };
}

function summary(over: Partial<ExportSummary>): ExportSummary {
  return {
    idea_id: "i1",
    status: "succeeded",
    project_url: "https://linear.app/x/project/p",
    created: 4,
    updated: 1,
    links: 2,
    failed: [],
    finished_at: "2026-11-25T00:00:00Z",
    ...over,
  };
}

describe("exportStatusView", () => {
  test("is idle with no run and no stored export", () => {
    expect(exportStatusView(null, null)).toEqual({ kind: "idle" });
  });

  test("shows progress while the run is active and has saved something", () => {
    expect(exportStatusView(live({ progress: PROGRESS }), null)).toEqual({ kind: "running", progress: PROGRESS });
  });

  test("a live finish is a success with an https project url only", () => {
    const finish = { projectUrl: "https://linear.app/p", created: 5, updated: 0, links: 1 };
    expect(exportStatusView(live({ status: "succeeded", finish }), null)).toMatchObject({ kind: "succeeded", projectUrl: "https://linear.app/p" });
    expect(exportStatusView(live({ finish: { ...finish, projectUrl: "javascript:alert(1)" } }), null)).toMatchObject({ projectUrl: null });
  });

  test("a failed export run shows the stored counts and failed items, with Retry", () => {
    const stored = summary({ status: "partial", failed: [{ kind: "issue", name: "T1", reason: "rate_limited" }] });
    const view = exportStatusView(live({ status: "failed", error: { code: "export.partial", message: "Some items could not be saved" } }), stored);
    expect(view).toMatchObject({ kind: "failed", reconnect: false, created: 4, failed: [{ name: "T1" }] });
  });

  test("a failure before anything was saved does not borrow an older export's counts", () => {
    const older = summary({ status: "succeeded" });
    const view = exportStatusView(live({ status: "failed", error: { code: "export.no_linear_team", message: "No team" } }), older);
    expect(view).toMatchObject({ kind: "failed", created: 0, updated: 0, links: 0, failed: [], projectUrl: null });
  });

  test("a lapsed connection asks to reconnect", () => {
    const view = exportStatusView(live({ status: "failed", error: { code: "mcp.expired", message: "Expired" } }), null);
    expect(view).toMatchObject({ kind: "failed", reconnect: true });
  });

  test("a failed run that is not about the export does not become an export failure", () => {
    expect(exportStatusView(live({ status: "failed", error: { code: "run.failed", message: "x" } }), null)).toEqual({ kind: "idle" });
    expect(exportStatusView(live({ status: "failed", error: { code: "provider.llm_not_ready", message: "x" } }), null)).toEqual({ kind: "idle" });
  });

  test("after a reload the stored result decides", () => {
    expect(exportStatusView(null, summary({}))).toMatchObject({ kind: "succeeded", created: 4 });
    expect(exportStatusView(null, summary({ status: "failed", project_url: null }))).toMatchObject({ kind: "failed", reconnect: false });
  });
});

describe("progress text", () => {
  test("percent is bounded and safe for a zero total", () => {
    expect(progressPercent(PROGRESS)).toBe(25);
    expect(progressPercent({ ...PROGRESS, done: 99, total: 12 })).toBe(100);
  });

  test("the line names the item and the action", () => {
    expect(progressLine(PROGRESS)).toBe("Issue created · Build the API");
    expect(progressLine({ ...PROGRESS, item: "links", action: "create", name: "" })).toBe("Blocked-by links created");
  });
});
