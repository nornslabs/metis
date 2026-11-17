import { describe, expect, it } from "vitest";

import {
  ApiError,
  errorMessage,
  fieldErrors,
  isSessionError,
  parseApiError,
  upstreamReason,
} from "./errors";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status });
}

describe("parseApiError", () => {
  it("maps a problem body to ApiError", async () => {
    const error = await parseApiError(
      json(422, {
        title: "Validation Failed",
        status: 422,
        code: "common.validation_failed",
        detail: "bad",
        request_id: "r1",
        retryable: false,
        errors: [{ field: "body.email", message: "Invalid" }],
      }),
    );
    expect(error).toMatchObject({
      status: 422,
      code: "common.validation_failed",
      title: "Validation Failed",
      detail: "bad",
      request_id: "r1",
      retryable: false,
      errors: [{ field: "body.email", message: "Invalid" }],
    });
  });

  it("falls back to common.unexpected with the HTTP status for a bad body", async () => {
    const error = await parseApiError(json(502, { nope: true }));
    expect(error).toMatchObject({ status: 502, code: "common.unexpected", errors: [] });
  });

  it("uses the HTTP status even when the body status disagrees", async () => {
    const error = await parseApiError(
      json(401, { title: "t", status: 500, code: "auth.not_signed_in" }),
    );
    expect(error.status).toBe(401);
  });
});

describe("isSessionError", () => {
  it.each(["auth.not_signed_in", "auth.session_expired"])("is true for %s", (code) => {
    expect(isSessionError(new ApiError({ status: 401, code, title: "t" }))).toBe(true);
  });

  it("is false for other codes and non-errors", () => {
    expect(isSessionError(new ApiError({ status: 403, code: "auth.csrf_failed", title: "t" }))).toBe(
      false,
    );
    expect(isSessionError(new Error("x"))).toBe(false);
  });
});

describe("fieldErrors / errorMessage", () => {
  const error = new ApiError({
    status: 422,
    code: "common.validation_failed",
    title: "Validation Failed",
    detail: null,
    errors: [
      { field: "body.email", message: "Invalid" },
      { field: "name", message: "Required" },
    ],
  });

  it("maps errors[] to setError inputs, dropping the location prefix", () => {
    expect(fieldErrors(error)).toEqual([
      { name: "email", error: { type: "server", message: "Invalid" } },
      { name: "name", error: { type: "server", message: "Required" } },
    ]);
  });

  it("prefers detail over title", () => {
    expect(errorMessage(error)).toBe("Validation Failed");
    expect(errorMessage(new ApiError({ status: 400, code: "x", title: "T", detail: "D" }))).toBe(
      "D",
    );
  });
});

describe("upstream errors", () => {
  it("reads meta.reason from a problem body", async () => {
    const response = new Response(
      JSON.stringify({
        title: "Provider error",
        code: "provider.upstream_error",
        meta: { provider: "llm", reason: "unauthorized" },
      }),
      { status: 502 },
    );
    const error = await parseApiError(response);
    expect(upstreamReason(error)).toBe("unauthorized");
  });

  it("has no reason without meta", async () => {
    const error = await parseApiError(new Response("nope", { status: 500 }));
    expect(upstreamReason(error)).toBeNull();
  });
});
