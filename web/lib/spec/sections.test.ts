import { describe, expect, it } from "vitest";

import { applySectionEdit, joinItems, listItems, sectionText, visibleSections } from "./sections";

const SPEC = [
  "## Problem",
  "",
  "Founders waste weeks.",
  "",
  "## Target users",
  "",
  "Solo founders.",
  "",
  "## Solution",
  "",
  "None.",
  "",
  "## Key features (MVP and later)",
  "",
  "- Interview",
  "- Research",
  "",
  "## Non-goals",
  "",
  "None.",
  "",
  "## Success metrics",
  "",
  "50 plans in a month.",
  "",
  "## Risks",
  "",
  "Churn.",
  "",
  "## Team notes",
  "",
  "Keep this exactly.",
  "",
].join("\n");

describe("sectionText", () => {
  it("reads the text under a template heading and treats None. as empty", () => {
    expect(sectionText(SPEC, "problem")).toBe("Founders waste weeks.");
    expect(sectionText(SPEC, "solution")).toBe("");
    expect(sectionText(SPEC, "competitive_edge")).toBe("");
  });
});

describe("visibleSections", () => {
  it("always shows the five named sections and only the filled extras", () => {
    const labels = visibleSections(SPEC).map((view) => view.label);
    expect(labels).toEqual(["Problem", "Users", "Core features", "Success metric", "Out of scope", "Risks"]);
  });

  it("lists bullet sections as items and falls back to text when the section is not all bullets", () => {
    const features = visibleSections(SPEC).find((view) => view.key === "key_features");
    expect(features).toMatchObject({ kind: "list", items: ["Interview", "Research"] });
    const prose = applySectionEdit(SPEC, "key_features", "MVP: interview.\n- Research");
    expect(visibleSections(prose).find((view) => view.key === "key_features")).toMatchObject({ kind: "text" });
  });

  it("shows an empty list section with no items", () => {
    expect(visibleSections(SPEC).find((view) => view.key === "non_goals")).toMatchObject({ kind: "list", items: [] });
  });
});

describe("applySectionEdit", () => {
  it("changes only its own block, byte for byte elsewhere, including unknown headings", () => {
    const edited = applySectionEdit(SPEC, "problem", "A new problem.");
    expect(edited).toContain("## Problem\n\nA new problem.\n\n## Target users");
    expect(edited.replace("A new problem.", "Founders waste weeks.")).toBe(SPEC);
    expect(edited).toContain("## Team notes\n\nKeep this exactly.\n");
  });

  it("writes None. for an empty section", () => {
    expect(sectionText(applySectionEdit(SPEC, "problem", "  "), "problem")).toBe("");
    expect(applySectionEdit(SPEC, "problem", "")).toContain("## Problem\n\nNone.\n");
  });

  it("keeps the trailing text of the last block", () => {
    const edited = applySectionEdit(SPEC, "risks", "Burnout.");
    expect(edited).toContain("## Risks\n\nBurnout.\n\n## Team notes");
  });

  it("adds a block for a template section the text lacks", () => {
    const edited = applySectionEdit("## Problem\n\nP.\n", "risks", "R.");
    expect(edited).toBe("## Problem\n\nP.\n\n## Risks\n\nR.\n");
  });

  it("returns the text unchanged for a key it does not know", () => {
    expect(applySectionEdit(SPEC, "nope", "x")).toBe(SPEC);
  });

  it("does not change its input and round-trips an unchanged section", () => {
    const copy = `${SPEC}`;
    applySectionEdit(SPEC, "problem", "x");
    expect(SPEC).toBe(copy);
    expect(applySectionEdit(SPEC, "problem", "Founders waste weeks.")).toBe(SPEC);
  });
});

describe("list items", () => {
  it("reads bullets and rejects text that is not all bullets", () => {
    expect(listItems("- a\n* b")).toEqual(["a", "b"]);
    expect(listItems("- a\nplain")).toBeNull();
    expect(listItems("")).toEqual([]);
  });

  it("joins non-empty items as bullets", () => {
    expect(joinItems(["a", " ", "b "])).toBe("- a\n- b");
    expect(joinItems([""])).toBe("");
  });
});
