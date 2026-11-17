import { describe, expect, test } from "vitest";

import { TITLE_MAX, deriveTitle, ideaFormSchema, toNewIdea } from "./idea-form";

describe("deriveTitle", () => {
  test("uses the first non-empty line, trimmed", () => {
    expect(deriveTitle("\n\n  A habit tracker  \nfor remote teams")).toBe("A habit tracker");
  });

  test("cuts a long first line to the title limit", () => {
    const title = deriveTitle(`${"x".repeat(200)}\nmore`);
    expect(title).toHaveLength(TITLE_MAX);
  });

  test("is empty for blank text", () => {
    expect(deriveTitle("  \n \n")).toBe("");
  });
});

describe("ideaFormSchema", () => {
  test("accepts an idea of ten characters or more with a usable first line", () => {
    expect(ideaFormSchema.safeParse({ text: "A habit tracker for teams" }).success).toBe(true);
  });

  test("rejects text shorter than ten characters after trimming", () => {
    const result = ideaFormSchema.safeParse({ text: "   short   " });
    expect(result.success).toBe(false);
  });

  test("rejects text longer than ten thousand characters", () => {
    const result = ideaFormSchema.safeParse({ text: "a".repeat(10_001) });
    expect(result.success).toBe(false);
  });

  test("rejects a first line under three characters even when the text is long enough", () => {
    const result = ideaFormSchema.safeParse({ text: "ab\nthe rest of a long description" });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toMatch(/first line/i);
  });
});

describe("toNewIdea", () => {
  test("sends the trimmed text and the derived title", () => {
    expect(toNewIdea({ text: "  Lab gear market\nused equipment  " })).toEqual({
      title: "Lab gear market",
      raw_text: "Lab gear market\nused equipment",
    });
  });
});
