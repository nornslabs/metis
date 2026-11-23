import { describe, expect, it } from "vitest";

import { buildSourceIndex, evidenceSources, normalizeSourceUrl } from "./sources";
import type { ResearchView } from "./view";

const item = (kind: string, url: string | null, title = "t") =>
  ({ id: title, kind, title, url, published_at: null, quote: null, claim: "c", confidence: 0.5 }) as ResearchView["items"][number];
const competitor = (url: string, name: string) =>
  ({ id: name, name, url, domain: "x", description: null, pricing: null, overlap: 0.5, updated_at: "" }) as ResearchView["competitors"][number];
const view = (items: ResearchView["items"], competitors: ResearchView["competitors"] = []): ResearchView =>
  ({ id: "s", idea_id: "i", run_id: "r", summary: null, closed_at: null, created_at: "", items, competitors }) as ResearchView;

describe("normalizeSourceUrl", () => {
  it("drops the fragment and a trailing slash", () => {
    expect(normalizeSourceUrl("https://a.com/x/#top")).toBe("https://a.com/x");
    expect(normalizeSourceUrl("https://a.com")).toBe("https://a.com");
  });

  it("keeps the query and rejects links that are not http(s)", () => {
    expect(normalizeSourceUrl("https://a.com/x?id=1")).toBe("https://a.com/x?id=1");
    expect(normalizeSourceUrl("javascript:alert(1)")).toBeNull();
    expect(normalizeSourceUrl(null)).toBeNull();
  });
});

describe("buildSourceIndex", () => {
  it("numbers competitors, then items, then score evidence", () => {
    const index = buildSourceIndex(
      view([item("market_fact", "https://facts.com/a", "Fact page")], [competitor("https://rival.com", "Rival")]),
      [{ url: "https://extra.com/p", title: "Extra" }],
    );
    expect(index.entries.map((entry) => [entry.number, entry.title, entry.domain])).toEqual([
      [1, "Rival", "rival.com"],
      [2, "Fact page", "facts.com"],
      [3, "Extra", "extra.com"],
    ]);
  });

  it("gives one page one number however its URL is spelled", () => {
    const index = buildSourceIndex(view([item("market_fact", "https://a.com/x/#y", "Item")], [competitor("https://a.com/x", "Comp")]), [
      { url: "https://a.com/x", title: "Evidence" },
    ]);
    expect(index.entries).toHaveLength(1);
    expect(index.entries[0]?.title).toBe("Comp");
    expect(index.numberFor("https://a.com/x#z")).toBe(1);
  });

  it("skips unsafe and missing URLs and never lists trends or risks", () => {
    const index = buildSourceIndex(
      view([item("market_fact", "javascript:alert(1)"), item("market_fact", null), item("trend", "https://t.com"), item("risk", "https://r.com")]),
    );
    expect(index.entries).toEqual([]);
    expect(index.numberFor("https://t.com")).toBeNull();
  });

  it("falls back to the domain for an empty title and keeps numbers when evidence is added", () => {
    const research = view([item("market_fact", "https://a.com/p", "  ")]);
    expect(buildSourceIndex(research).entries[0]?.title).toBe("a.com");
    const withEvidence = buildSourceIndex(research, [{ url: "https://b.com", title: "B" }]);
    expect(withEvidence.numberFor("https://a.com/p")).toBe(1);
    expect(withEvidence.numberFor("https://b.com")).toBe(2);
  });

  it("works without research (evidence only)", () => {
    expect(buildSourceIndex(null, [{ url: "https://b.com", title: "B" }]).numberFor("https://b.com")).toBe(1);
  });
});

describe("evidenceSources", () => {
  it("lists the cited pages in parameter order and skips no-evidence parameters", () => {
    const sources = evidenceSources([
      { no_evidence: false, evidence: [{ url: "https://a.com", title: "A" }] },
      { no_evidence: true, evidence: [{ url: "https://skipped.com", title: "S" }] },
      { no_evidence: false, evidence: [{ url: "https://b.com", title: "B" }] },
    ]);
    expect(sources.map((source) => source.url)).toEqual(["https://a.com", "https://b.com"]);
  });
});
