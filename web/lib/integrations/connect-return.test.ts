import { describe, expect, test } from "vitest";

import {
  connectErrorMessage,
  connectRedirectPath,
  readConnectReturn,
  withoutConnectReturn,
} from "./connect-return";

describe("readConnectReturn", () => {
  test("reads a successful return", () => {
    expect(readConnectReturn(new URLSearchParams("settings=integrations&integration=linear"))).toEqual({ kind: "connected" });
  });

  test("reads an error return, which wins over a success mark", () => {
    expect(readConnectReturn(new URLSearchParams("integration=linear&integration_error=mcp.oauth_failed"))).toEqual({
      kind: "error",
      code: "mcp.oauth_failed",
    });
  });

  test("returns null when the URL has no return params or names another provider", () => {
    expect(readConnectReturn(new URLSearchParams("settings=integrations"))).toBeNull();
    expect(readConnectReturn(new URLSearchParams("integration=notion"))).toBeNull();
  });
});

describe("URL helpers", () => {
  test("withoutConnectReturn drops only the return params", () => {
    const search = new URLSearchParams("settings=integrations&integration=linear&panel=plan");
    expect(withoutConnectReturn("/ideas/1", search)).toBe("/ideas/1?settings=integrations&panel=plan");
  });

  test("connectRedirectPath opens the Integrations tab on this page and keeps other params", () => {
    expect(connectRedirectPath("/ideas/1", new URLSearchParams("panel=plan&integration=linear"))).toBe(
      "/ideas/1?panel=plan&settings=integrations",
    );
  });

  test("connectErrorMessage falls back for an unknown code", () => {
    expect(connectErrorMessage("mcp.oauth_failed")).toBe("Linear did not accept the connection.");
    expect(connectErrorMessage("something.else")).toBe("Linear could not be connected. Try again.");
  });
});
