import { describe, expect, test } from "vitest";

import { OUTPUT_PANES, parseOutputPane, withOutputPane } from "./panes";

describe("parseOutputPane", () => {
  test.each(OUTPUT_PANES)("accepts the %s pane", (pane) => {
    expect(parseOutputPane(pane)).toBe(pane);
  });

  test.each([null, "", "nope", "Score", "score "])("returns null for %j", (value) => {
    expect(parseOutputPane(value)).toBeNull();
  });
});

describe("withOutputPane", () => {
  test("sets the param and keeps the other params", () => {
    const url = withOutputPane("/ideas/1", new URLSearchParams("settings=keys"), "spec");

    expect(url).toBe("/ideas/1?settings=keys&panel=spec");
  });

  test("replaces an earlier pane", () => {
    expect(withOutputPane("/ideas/1", new URLSearchParams("panel=score"), "plan")).toBe("/ideas/1?panel=plan");
  });

  test("removes the param and leaves a bare path when nothing else is set", () => {
    expect(withOutputPane("/ideas/1", new URLSearchParams("panel=score"), null)).toBe("/ideas/1");
  });
});
