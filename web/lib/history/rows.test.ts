import { describe, expect, it } from "vitest";

import type { components } from "@/lib/api/schema";
import type { ExportSummary } from "@/lib/schemas/export";

import { toHistoryRow } from "./rows";

type Idea = components["schemas"]["Idea"];

const IDEA: Idea = {
  id: "i1",
  workspace_id: "w1",
  created_by: "u1",
  title: "Pocket CRM",
  raw_text: "A tiny CRM for freelancers.",
  kind: null,
  stage: "scoring",
  current_score: 63,
  version: 1,
  created_at: "2026-11-20T10:00:00Z",
  updated_at: "2026-11-22T10:00:00Z",
};

describe("toHistoryRow", () => {
  it("takes score, band and totals from the summary", () => {
    const row = toHistoryRow(IDEA, { idea_id: "i1", band: "promising", totals: [54, 63] });

    expect(row).toMatchObject({ id: "i1", score: 63, band: "promising", totals: [54, 63], activeAt: IDEA.updated_at });
  });

  it("falls back to the idea's current score with no summary yet", () => {
    const row = toHistoryRow(IDEA, undefined);

    expect(row).toMatchObject({ score: 63, band: null, totals: [] });
  });

  it("has no score for an unscored idea", () => {
    const row = toHistoryRow({ ...IDEA, current_score: null }, undefined);

    expect(row.score).toBeNull();
  });
});

describe("toHistoryRow export link", () => {
  const exported: ExportSummary = {
    idea_id: "i1",
    status: "succeeded",
    project_url: "https://linear.app/x/project/p",
    created: 3,
    updated: 0,
    links: 1,
    failed: [],
    finished_at: "2026-11-25T00:00:00Z",
  };

  it("links to the Linear project after a clean export", () => {
    expect(toHistoryRow(IDEA, undefined, exported).exportUrl).toBe("https://linear.app/x/project/p");
  });

  it("has no link for a partial export, no export, or a URL that is not https", () => {
    expect(toHistoryRow(IDEA, undefined, { ...exported, status: "partial" }).exportUrl).toBeNull();
    expect(toHistoryRow(IDEA, undefined, undefined).exportUrl).toBeNull();
    expect(toHistoryRow(IDEA, undefined, { ...exported, project_url: "javascript:alert(1)" }).exportUrl).toBeNull();
  });
});

