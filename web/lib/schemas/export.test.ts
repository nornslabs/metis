import { describe, expect, test } from "vitest";

import {
  exportDecisionSchema,
  exportPreviewSchema,
  exportSummarySchema,
  safeProjectUrl,
  teamChoiceSchema,
} from "./export";

describe("safeProjectUrl", () => {
  test("accepts https and refuses other schemes, bad text and null", () => {
    expect(safeProjectUrl("https://linear.app/p")).toBe("https://linear.app/p");
    expect(safeProjectUrl("http://linear.app/p")).toBeNull();
    expect(safeProjectUrl("javascript:alert(1)")).toBeNull();
    expect(safeProjectUrl("not a url")).toBeNull();
    expect(safeProjectUrl(null)).toBeNull();
  });
});

describe("resume payloads", () => {
  test("a team choice needs a team id", () => {
    expect(teamChoiceSchema.safeParse({ team_id: "t1" }).success).toBe(true);
    expect(teamChoiceSchema.safeParse({ team_id: "" }).success).toBe(false);
  });

  test("an export decision must say approved true or false by name", () => {
    expect(exportDecisionSchema.safeParse({ approved: false }).success).toBe(true);
    expect(exportDecisionSchema.safeParse(true).success).toBe(false);
  });

  test("a project name is trimmed and must be 1 to 80 characters", () => {
    expect(exportDecisionSchema.parse({ approved: true, project_name: "  Metis  " }).project_name).toBe("Metis");
    expect(exportDecisionSchema.safeParse({ approved: true, project_name: "   " }).success).toBe(false);
    expect(
      exportDecisionSchema.safeParse({
        approved: true,
        project_name: "a".repeat(80),
      }).success,
    ).toBe(true);
    expect(
      exportDecisionSchema.safeParse({
        approved: true,
        project_name: "a".repeat(81),
      }).success,
    ).toBe(false);
  });
});

describe("exportSummarySchema", () => {
  test("reads a partial export with its failed items", () => {
    const parsed = exportSummarySchema.parse({
      idea_id: "i1",
      status: "partial",
      project_url: null,
      created: 1,
      updated: 0,
      links: 0,
      failed: [{ kind: "issue", name: "T1", reason: "timeout" }],
      finished_at: null,
    });
    expect(parsed.failed).toHaveLength(1);
  });

  test("refuses a status the server never sends", () => {
    expect(exportSummarySchema.safeParse({ idea_id: "i1", status: "running" }).success).toBe(false);
  });
});

describe("exportPreviewSchema", () => {
  const base = {
    team: { id: "t", name: "Ship" },
    plan_version: 1,
    project: { name: "Metis", action: "create" },
    milestones: { total: 0, create: 0, update: 0, items: [] },
    issues: { total: 1, create: 1, update: 0 },
    blocked_by_links: 0,
    labels: { total: 0, items: [] },
  };

  test("reads a preview saved before briefs and the HLD existed", () => {
    const parsed = exportPreviewSchema.parse(base);
    expect(parsed.issues.items).toEqual([]);
    expect(parsed.hld).toBeUndefined();
  });

  test("reads issue briefs, their component and the HLD", () => {
    const parsed = exportPreviewSchema.parse({
      ...base,
      hld: { title: "Metis HLD", action: "create" },
      issues: {
        ...base.issues,
        items: [{ title: "T1", description: "## Goal", component: "Auth" }],
      },
    });
    expect(parsed.hld?.title).toBe("Metis HLD");
    expect(parsed.issues.items[0]?.component).toBe("Auth");
  });
});
