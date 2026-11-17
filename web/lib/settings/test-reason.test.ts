import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/errors";

import { testFailureMessage } from "./test-reason";

function upstream(reason?: string) {
  return new ApiError({
    status: 502,
    code: "provider.upstream_error",
    title: "Provider error",
    meta: reason ? { provider: "llm", reason } : {},
  });
}

describe("testFailureMessage", () => {
  it("explains a known upstream reason", () => {
    expect(testFailureMessage(upstream("unauthorized"))).toBe("The provider rejected the key.");
    expect(testFailureMessage(upstream("unreachable"))).toContain("base URL");
  });

  it("falls back to the API message for an unknown reason", () => {
    expect(testFailureMessage(upstream("odd"))).toBe("Provider error");
  });

  it("handles a non-API error", () => {
    expect(testFailureMessage(new Error("x"))).toBe("Couldn't test the key. Try again.");
  });
});
