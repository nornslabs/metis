import { describe, expect, it } from "vitest";

import { initialsOf } from "./user-avatar";

describe("initialsOf", () => {
  it("uses the first letters of the first two words", () => {
    expect(initialsOf("Ada Lovelace King", "a@x.test")).toBe("AL");
  });

  it("uses one letter for a one-word name", () => {
    expect(initialsOf("sboy99", "a@x.test")).toBe("S");
  });

  it("falls back to the email without a name", () => {
    expect(initialsOf(null, "zed@x.test")).toBe("Z");
    expect(initialsOf("  ", "zed@x.test")).toBe("Z");
  });
});
