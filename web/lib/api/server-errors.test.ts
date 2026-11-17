import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
const { redirect } = vi.hoisted(() => ({
  redirect: vi.fn((url: string) => {
    throw new Error(`NEXT_REDIRECT ${url}`);
  }),
}));
vi.mock("next/navigation", () => ({ redirect }));

import { ApiError } from "./errors";
import { redirectIfSignedOut } from "./server-errors";

beforeEach(() => {
  redirect.mockClear();
});

describe("redirectIfSignedOut", () => {
  it("redirects to sign-in, remembering the path, on a session error", () => {
    const error = new ApiError({ status: 401, code: "auth.session_expired", title: "t" });
    expect(() => redirectIfSignedOut(error, "/ideas/1")).toThrow("NEXT_REDIRECT");
    expect(redirect).toHaveBeenCalledWith("/sign-in?redirect_to=%2Fideas%2F1");
  });

  it("rethrows any other error", () => {
    const error = new ApiError({ status: 409, code: "run.already_running", title: "t" });
    expect(() => redirectIfSignedOut(error)).toThrow(error);
    expect(redirect).not.toHaveBeenCalled();
  });
});
