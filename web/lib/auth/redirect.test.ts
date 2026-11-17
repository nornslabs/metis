import { describe, expect, it } from "vitest";

import { DEFAULT_REDIRECT, safeRedirectPath, signInHref } from "./redirect";

describe("safeRedirectPath", () => {
  it("keeps a relative path with its query", () => {
    expect(safeRedirectPath("/ideas/abc?x=1")).toBe("/ideas/abc?x=1");
  });

  it("falls back to the default when the value is missing", () => {
    expect(safeRedirectPath(undefined)).toBe(DEFAULT_REDIRECT);
    expect(safeRedirectPath("")).toBe(DEFAULT_REDIRECT);
  });

  it.each([
    "https://evil.com",
    "//evil.com",
    "/\\evil.com",
    "javascript:alert(1)",
    "ideas/abc",
    "/ok\nHeader: x",
  ])("rejects %j", (value) => {
    expect(safeRedirectPath(value)).toBe(DEFAULT_REDIRECT);
  });

  it("takes the first value when the parameter repeats", () => {
    expect(safeRedirectPath(["/a", "//evil.com"])).toBe("/a");
  });

  it("never sends a signed-in user back to the sign-in page", () => {
    expect(safeRedirectPath("/sign-in?redirect_to=/x")).toBe(DEFAULT_REDIRECT);
  });
});

describe("signInHref", () => {
  it("encodes the path the user asked for", () => {
    expect(signInHref("/ideas/a b")).toBe(
      "/sign-in?redirect_to=%2Fideas%2Fa%20b",
    );
  });

  it("omits the parameter for the default path", () => {
    expect(signInHref("/")).toBe("/sign-in");
  });
});
