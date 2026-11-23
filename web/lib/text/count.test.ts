import { describe, expect, it } from "vitest";

import { countOf } from "./count";

describe("countOf", () => {
  it("uses the singular for one and the plural otherwise", () => {
    expect(countOf(1, "source")).toBe("1 source");
    expect(countOf(0, "source")).toBe("0 sources");
    expect(countOf(6, "source")).toBe("6 sources");
  });
});
