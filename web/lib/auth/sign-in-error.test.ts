import { describe, expect, it } from "vitest";

import { GENERIC_SIGN_IN_ERROR, signInErrorMessage } from "./sign-in-error";

describe("signInErrorMessage", () => {
  it.each([
    ["auth.oauth_state_invalid", "Your sign-in link expired. Try again."],
    ["auth.oauth_failed", "Google sign-in failed. Try again."],
    ["auth.email_unverified", "Your Google email is not verified."],
  ])("maps %s", (code, message) => {
    expect(signInErrorMessage(code)).toBe(message);
  });

  it("uses a generic message for an unknown code", () => {
    expect(signInErrorMessage("something.else")).toBe(GENERIC_SIGN_IN_ERROR);
  });

  it("returns nothing when there is no error", () => {
    expect(signInErrorMessage(undefined)).toBeNull();
    expect(signInErrorMessage("")).toBeNull();
  });
});
