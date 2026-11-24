import { describe, expect, it } from "vitest";

import { specConfirmedSchema, specOverviewSchema, specVersionListSchema } from "./spec";

const version = {
  id: "v1",
  idea_id: "i",
  number: 1,
  source: "agent",
  content_md: "## Problem\n\nP.\n",
  sections: { problem: "P." },
  run_id: null,
  created_by: null,
  created_at: "2026-11-23T10:00:00Z",
};

describe("spec schemas", () => {
  it("reads an overview with no versions yet", () => {
    expect(specOverviewSchema.parse({ latest: null, confirmed: null })).toEqual({ latest: null, confirmed: null });
  });

  it("reads a confirmation with the run it resumed", () => {
    expect(specConfirmedSchema.parse({ confirmed: version, run_id: "r1" }).run_id).toBe("r1");
  });

  it("rejects a version with an unknown author or a bad number", () => {
    expect(() => specOverviewSchema.parse({ latest: { ...version, source: "bot" }, confirmed: null })).toThrow();
    expect(() => specOverviewSchema.parse({ latest: { ...version, number: 0 }, confirmed: null })).toThrow();
  });
});

describe("specVersionListSchema", () => {
  const row = { id: "sv2", number: 2, source: "user", created_by: "u1", created_at: "2026-11-23T10:00:00Z" };

  it("reads the version list the server sends", () => {
    const list = specVersionListSchema.parse({ items: [row, { ...row, id: "sv1", number: 1, source: "agent", created_by: null }] });
    expect(list.items.map((item) => item.number)).toEqual([2, 1]);
  });

  it("rejects a version number that is not positive", () => {
    expect(() => specVersionListSchema.parse({ items: [{ ...row, number: 0 }] })).toThrow();
  });

  it("rejects an unknown source", () => {
    expect(() => specVersionListSchema.parse({ items: [{ ...row, source: "bot" }] })).toThrow();
  });
});
