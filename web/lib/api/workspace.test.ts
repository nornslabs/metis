import { describe, expect, it } from "vitest";

import { parseWorkspaceCookie, serializeWorkspaceCookie } from "./workspace";

describe("workspace cookie", () => {
  it("reads the id among other cookies", () => {
    expect(parseWorkspaceCookie("a=1; metis_workspace=ws-1; b=2")).toBe("ws-1");
  });

  it("is null when absent or empty", () => {
    expect(parseWorkspaceCookie("a=1")).toBeNull();
    expect(parseWorkspaceCookie("metis_workspace=")).toBeNull();
  });

  it("round-trips an id", () => {
    const cookie = serializeWorkspaceCookie("ws 1");
    expect(parseWorkspaceCookie(cookie.split(";")[0])).toBe("ws 1");
  });

  it("is readable by scripts, lax, site-wide and lasts a year", () => {
    const cookie = serializeWorkspaceCookie("ws-1");
    expect(cookie).not.toMatch(/HttpOnly/i);
    expect(cookie).toContain("SameSite=Lax");
    expect(cookie).toContain("Path=/");
    expect(cookie).toContain("Max-Age=31536000");
  });

  it("clearing expires the cookie", () => {
    expect(serializeWorkspaceCookie(null)).toContain("Max-Age=0");
  });
});
