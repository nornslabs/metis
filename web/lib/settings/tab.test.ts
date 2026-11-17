import { describe, expect, it } from "vitest";

import { parseSettingsTab, withSettingsTab } from "./tab";

describe("parseSettingsTab", () => {
  it("is null without the param", () => {
    expect(parseSettingsTab(null)).toBeNull();
  });

  it("reads a known tab", () => {
    expect(parseSettingsTab("keys")).toBe("keys");
  });

  it("falls back to account for an unknown tab", () => {
    expect(parseSettingsTab("nope")).toBe("account");
  });
});

describe("withSettingsTab", () => {
  it("sets the param and keeps others", () => {
    expect(withSettingsTab("/ideas/1", new URLSearchParams("a=1"), "keys")).toBe(
      "/ideas/1?a=1&settings=keys",
    );
  });

  it("removes the param, and the question mark when nothing is left", () => {
    expect(withSettingsTab("/", new URLSearchParams("settings=keys"), null)).toBe("/");
  });
});
