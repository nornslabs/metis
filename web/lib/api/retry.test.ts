import { describe, expect, it } from "vitest";

import { ApiError } from "./errors";
import { shouldRetry } from "./retry";

const make = (status: number, retryable: boolean) =>
  new ApiError({ status, code: "x", title: "t", retryable });

describe("shouldRetry", () => {
  it("never retries a 4xx", () => {
    expect(shouldRetry(0, make(409, true))).toBe(false);
    expect(shouldRetry(0, make(404, false))).toBe(false);
  });

  it("retries a retryable 5xx up to twice", () => {
    expect(shouldRetry(0, make(503, true))).toBe(true);
    expect(shouldRetry(1, make(503, true))).toBe(true);
    expect(shouldRetry(2, make(503, true))).toBe(false);
  });

  it("does not retry a non-retryable 5xx", () => {
    expect(shouldRetry(0, make(500, false))).toBe(false);
  });
});
