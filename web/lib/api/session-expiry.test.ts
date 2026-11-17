import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./errors";
import { createSessionExpiryHandler } from "./session-expiry";

const expired = new ApiError({ status: 401, code: "auth.session_expired", title: "t" });

describe("createSessionExpiryHandler", () => {
  it("fires once for several concurrent session errors", () => {
    const onExpired = vi.fn();
    const { handle } = createSessionExpiryHandler(onExpired);
    handle(expired);
    handle(new ApiError({ status: 401, code: "auth.not_signed_in", title: "t" }));
    expect(onExpired).toHaveBeenCalledTimes(1);
  });

  it("ignores other errors", () => {
    const onExpired = vi.fn();
    const { handle } = createSessionExpiryHandler(onExpired);
    handle(new ApiError({ status: 409, code: "run.already_running", title: "t" }));
    handle(new Error("network"));
    expect(onExpired).not.toHaveBeenCalled();
  });

  it("fires again after rearm", () => {
    const onExpired = vi.fn();
    const { handle, rearm } = createSessionExpiryHandler(onExpired);
    handle(expired);
    rearm();
    handle(expired);
    expect(onExpired).toHaveBeenCalledTimes(2);
  });
});
