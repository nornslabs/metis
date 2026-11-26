import { describe, expect, test } from "vitest";

import { exportDecisionSchema, exportSummarySchema, safeProjectUrl, teamChoiceSchema } from "./export";

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
