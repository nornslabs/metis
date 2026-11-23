import { describe, expect, it } from "vitest";

import {
  competitorRelation,
  confidenceLabel,
  domainOf,
  formatPublished,
  marketFacts,
  overlapPercent,
  otherFindings,
  safeHref,
  type ResearchView,
} from "./view";

const item = (kind: string, url: string | null, id = "i") =>
  ({ id, kind, title: "t", url, published_at: null, quote: null, claim: "c", confidence: 0.5 }) as ResearchView["items"][number];
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

describe("competitorRelation", () => {
  it("is Direct from 0.5 overlap and Adjacent below", () => {
    expect(competitorRelation(0.5)).toBe("Direct");
    expect(competitorRelation(0.99)).toBe("Direct");
    expect(competitorRelation(0.49)).toBe("Adjacent");
    expect(competitorRelation(0)).toBe("Adjacent");
  });
});
