import { describe, expect, it } from "vitest";

import {
  confidenceLabel,
  domainOf,
  formatPublished,
  marketFacts,
  overlapPercent,
  otherFindings,
  safeHref,
  sourceChips,
  type ResearchView,
} from "./view";

const item = (kind: string, url: string | null, id = "i") =>
  ({ id, kind, title: "t", url, published_at: null, quote: null, claim: "c", confidence: 0.5 }) as ResearchView["items"][number];
const competitor = (url: string, name = "n") =>
  ({ id: name, name, url, domain: "x", description: null, pricing: null, overlap: 0.5, updated_at: "" }) as ResearchView["competitors"][number];
const view = (items: ResearchView["items"], competitors: ResearchView["competitors"] = []): ResearchView =>
  ({ id: "s", idea_id: "i", run_id: "r", summary: null, closed_at: null, created_at: "", items, competitors }) as ResearchView;

describe("safeHref and domainOf", () => {
  it("accepts http and https links only", () => {
    expect(safeHref("https://www.g2.com/products/x")).toBe("https://www.g2.com/products/x");
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("data:text/html,hi")).toBeNull();
    expect(safeHref("not a url")).toBeNull();
    expect(safeHref(null)).toBeNull();
  });

  it("drops www from the domain", () => {
    expect(domainOf("https://www.g2.com/x")).toBe("g2.com");
    expect(domainOf("ftp://g2.com")).toBeNull();
  });
});

describe("labels", () => {
  it("formats overlap as a percentage", () => {
    expect(overlapPercent(0.62)).toBe("62%");
    expect(overlapPercent(1)).toBe("100%");
  });

  it("buckets confidence", () => {
    expect(confidenceLabel(0.9)).toBe("High");
    expect(confidenceLabel(0.7)).toBe("High");
    expect(confidenceLabel(0.5)).toBe("Medium");
    expect(confidenceLabel(0.1)).toBe("Low");
  });

  it("formats a published date without shifting the day", () => {
    expect(formatPublished("2026-11-02")).toBe("Nov 2, 2026");
    expect(formatPublished(null)).toBeNull();
  });
});

describe("items", () => {
  it("splits facts from trends and risks", () => {
    const v = view([item("market_fact", "https://a.com"), item("trend", null), item("risk", null), item("competitor", "https://b.com")]);
    expect(marketFacts(v)).toHaveLength(1);
    expect(otherFindings(v)).toHaveLength(2);
  });
});

describe("sourceChips", () => {
  it("makes one chip per domain, competitors first", () => {
    const v = view([item("market_fact", "https://www.g2.com/a"), item("market_fact", "https://news.ycombinator.com/x")], [
      competitor("https://g2.com/b"),
      competitor("https://producthunt.com/c"),
    ]);
    const { chips, more } = sourceChips(v);
    expect(chips.map((chip) => chip.domain)).toEqual(["g2.com", "producthunt.com", "news.ycombinator.com"]);
    expect(chips[0]).toMatchObject({ letter: "G", href: "https://g2.com/b" });
    expect(more).toBe(0);
  });

  it("counts the chips left out", () => {
    const urls = ["a", "b", "c", "d", "e", "f", "g"].map((d) => competitor(`https://${d}.com`, d));
    const { chips, more } = sourceChips(view([], urls), 5);
    expect(chips).toHaveLength(5);
    expect(more).toBe(2);
  });

  it("skips unsafe and missing urls and ignores trends and risks", () => {
    const v = view([item("market_fact", "javascript:alert(1)"), item("market_fact", null), item("trend", "https://t.com")]);
    expect(sourceChips(v)).toEqual({ chips: [], more: 0 });
  });
});
