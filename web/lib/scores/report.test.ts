import { describe, expect, test } from "vitest";

import { buildScoreReport, reportFileName } from "@/lib/scores/report";
import { scoreVersions } from "@/lib/scores/versions";
import type { ScoreRun, Suggestion } from "@/lib/scores/view";

const PARAMS = ["problem_severity", "uniqueness", "market_demand", "value", "feasibility", "timing"] as const;

function score(id: string, total: number, raw: number): ScoreRun {
  return {
    id,
    idea_id: "i",
    run_id: "r",
    rubric_version: 1,
    total,
    band: "promising",
    trigger: "manual",
    created_at: "2026-11-20T10:00:00Z",
    weights: {},
    params: PARAMS.map((param, index) => ({
      param,
      raw,
      weight: 10 + index,
      weighted: raw,
      confidence: 0.8,
      reason: `Reason for ${param}`,
      no_evidence: index === 1,
      evidence: index === 1 ? [] : [{ title: "A source", url: "https://example.com/a", quote: "A quote" }],
    })),
  };
}

const SUGGESTION: Suggestion = {
  id: "s",
  idea_id: "i",
  score_run_id: "a",
  kind: "niche",
  title: "Focus on clinics",
  rationale: "Smaller market, clearer pain",
  expected_impact: "+6 on demand",
  target_params: ["market_demand"],
  evidence: [{ title: "Clinic study", url: "https://example.com/c", quote: "" }],
  status: "open",
  created_at: "2026-11-20T10:00:00Z",
};

const HISTORY = [
  { id: "b", idea_id: "i", run_id: "r", rubric_version: 1, total: 63, band: "promising" as const, trigger: "manual" as const, created_at: "2026-11-21T10:00:00Z" },
  { id: "a", idea_id: "i", run_id: "r", rubric_version: 1, total: 56, band: "promising" as const, trigger: "manual" as const, created_at: "2026-11-20T10:00:00Z" },
];

describe("buildScoreReport", () => {
  const report = buildScoreReport({
    ideaTitle: "Habit tracker",
    score: score("b", 63, 6),
    versions: scoreVersions(HISTORY),
    suggestions: [SUGGESTION],
  });

  test("states the total, band, version and delta", () => {
    expect(report).toContain("**63 / 100** · Promising · v2 · ▲ 7");
  });

  test("lists all six parameters with their reasons", () => {
    expect(report).toContain("### Problem severity — 6/10");
    expect(report).toContain("Reason for timing");
    expect((report.match(/^### /gm) ?? []).length).toBe(6);
  });

  test("marks a parameter without evidence as a guess and links the others", () => {
    expect(report).toContain("No evidence: this mark is a guess.");
    expect(report).toContain("[A source](https://example.com/a) — “A quote”");
  });

  test("includes history and suggestions", () => {
    expect(report).toContain("- v1: 56 (Promising)");
    expect(report).toContain("**Niche: Focus on clinics**");
    expect(report).toContain("Expected impact: +6 on demand");
  });

  test("leaves out empty sections", () => {
    const bare = buildScoreReport({ ideaTitle: "x", score: score("a", 56, 5), versions: scoreVersions(HISTORY.slice(1)), suggestions: [] });
    expect(bare).not.toContain("## History");
    expect(bare).not.toContain("## Suggestions");
  });
});

describe("reportFileName", () => {
  test("slugs the title", () => {
    expect(reportFileName("Habit tracker for remote teams!")).toBe("metis-habit-tracker-for-remote-teams-score.md");
  });

  test("falls back when the title has no usable characters", () => {
    expect(reportFileName("???")).toBe("metis-idea-score.md");
  });
});
