import { describe, expect, it } from "vitest";

import { diffSpecs, isUnchanged } from "@/lib/spec/diff";

function spec(parts: { problem?: string; features?: string; extra?: string }): string {
  return [
    "## Problem",
    "",
    parts.problem ?? "None.",
    "",
    "## Key features (MVP and later)",
    "",
    parts.features ?? "None.",
    "",
    ...(parts.extra === undefined ? [] : ["## Notes", "", parts.extra, ""]),
  ].join("\n");
}

const find = (md: { a: string; b: string }, key: string) => diffSpecs(md.a, md.b).sections.find((section) => section.key === key)!;

describe("diffSpecs", () => {
  it("reports no change for identical text", () => {
    const md = spec({ problem: "Founders waste weeks.", features: "- One\n- Two" });
    const diff = diffSpecs(md, md);
    expect(diff.inserted).toBe(0);
    expect(diff.deleted).toBe(0);
    expect(diff.sections.every(isUnchanged)).toBe(true);
  });

  it("marks a replaced word as one deletion and one insertion", () => {
    const change = find({ a: spec({ problem: "Founders waste weeks." }), b: spec({ problem: "Founders lose weeks." }) }, "problem");
    expect(change.ops).toEqual([
      { kind: "same", text: "Founders" },
      { kind: "del", text: "waste" },
      { kind: "ins", text: "lose" },
      { kind: "same", text: "weeks." },
    ]);
    expect([change.inserted, change.deleted]).toEqual([1, 1]);
  });

  it("joins neighbouring added words into one run and counts each word", () => {
    const change = find({ a: spec({ problem: "A B" }), b: spec({ problem: "A new big B" }) }, "problem");
    expect(change.ops).toEqual([
      { kind: "same", text: "A" },
      { kind: "ins", text: "new big" },
      { kind: "same", text: "B" },
    ]);
    expect(change.inserted).toBe(2);
  });

  it("treats a section that was empty as all inserted", () => {
    const change = find({ a: spec({}), b: spec({ problem: "New text" }) }, "problem");
    expect(change.ops).toEqual([{ kind: "ins", text: "New text" }]);
    expect(change.deleted).toBe(0);
  });

  it("compares list sections item by item", () => {
    const change = find({ a: spec({ features: "- One\n- Two\n- Three" }), b: spec({ features: "- One\n- Three\n- Four" }) }, "key_features");
    expect(change.kind).toBe("list");
    expect(change.ops).toEqual([
      { kind: "same", text: "One" },
      { kind: "del", text: "Two" },
      { kind: "same", text: "Three" },
      { kind: "ins", text: "Four" },
    ]);
    expect([change.inserted, change.deleted]).toEqual([1, 1]);
  });

  it("falls back to text when a list section is not all bullets", () => {
    const change = find({ a: spec({ features: "- One" }), b: spec({ features: "One and more" }) }, "key_features");
    expect(change.kind).toBe("text");
    expect(change.inserted + change.deleted).toBeGreaterThan(0);
  });

  it("compares headings the template does not know as text", () => {
    const diff = diffSpecs(spec({ extra: "old note" }), spec({ extra: "new note" }));
    const other = diff.sections.find((section) => section.label === "Notes")!;
    expect(other.kind).toBe("text");
    expect([other.inserted, other.deleted]).toEqual([1, 1]);
  });

  it("shows optional sections only when either version has content", () => {
    const withRisks = (text: string) => `${spec({})}\n## Risks\n\n${text}\n`;
    const keys = (md: { a: string; b: string }) => diffSpecs(md.a, md.b).sections.map((section) => section.key);
    expect(keys({ a: withRisks("None."), b: withRisks("None.") })).not.toContain("risks");
    expect(keys({ a: withRisks("None."), b: withRisks("Churn") })).toContain("risks");
  });

  it("sums the counts over all sections and leaves its inputs alone", () => {
    const a = spec({ problem: "One", features: "- A" });
    const b = spec({ problem: "Two", features: "- A\n- B" });
    const diff = diffSpecs(a, b);
    expect([diff.inserted, diff.deleted]).toEqual([2, 1]);
    expect(a).toBe(spec({ problem: "One", features: "- A" }));
  });
});
