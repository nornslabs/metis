import { describe, expect, it } from "vitest";

import type { components } from "@/lib/api/schema";

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
