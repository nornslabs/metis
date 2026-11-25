import { describe, expect, test } from "vitest";

import { linearItemState } from "./menu-state";

describe("linearItemState", () => {
  test("is on with a plan, a connected Linear and no active run", () => {
    expect(linearItemState({ hasPlan: true, linear: "connected", runActive: false })).toEqual({ disabled: false, reason: null });
  });

  test.each([
    [{ hasPlan: false, linear: "connected", runActive: false }, "after the plan"],
    [{ hasPlan: true, linear: "not_connected", runActive: false }, "Connect Linear in Settings"],
    [{ hasPlan: true, linear: "expired", runActive: false }, "Reconnect Linear in Settings"],
    [{ hasPlan: true, linear: "connected", runActive: true }, "A run is in progress"],
  ] as const)("is off with a reason: %j", (input, reason) => {
    expect(linearItemState(input)).toEqual({ disabled: true, reason });
  });
});
