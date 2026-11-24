import { describe, expect, it } from "vitest";

import { buildSourcesReport, sourcesFileName } from "./sources-report";

describe("sourcesFileName", () => {
  it("slugs the idea title", () => {
    expect(sourcesFileName("Idea Validation, fast!")).toBe("metis-idea-validation-fast-sources.md");
    expect(sourcesFileName("***")).toBe("metis-idea-sources.md");
  });
});

describe("buildSourcesReport", () => {
  it("lists numbered links with their domains", () => {
    const report = buildSourcesReport("My idea", [
      { number: 1, href: "https://a.com/x", domain: "a.com", title: "Page [one]" },
      { number: 2, href: "https://b.com", domain: "b.com", title: "Two" },
    ]);
    expect(report).toContain("# Sources: My idea");
    expect(report).toContain("1. [Page one](<https://a.com/x>) — a.com");
    expect(report).toContain("2. [Two](<https://b.com>) — b.com");
  });

  it("says so when there are no sources", () => {
    expect(buildSourcesReport("x", [])).toContain("No sources.");
  });
});
