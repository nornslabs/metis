import { describe, expect, test } from "vitest";

import { gateItemLabel, nodeLabel, stageLabel } from "./labels";

describe("labels", () => {
  test("names known nodes and stages", () => {
    expect(nodeLabel("researcher")).toBe("Researcher");
    expect(stageLabel("spec_draft")).toBe("Spec draft");
  });

  test("title-cases unknown values", () => {
    expect(nodeLabel("market_watch")).toBe("Market watch");
    expect(stageLabel("archived")).toBe("Archived");
  });
});

describe("gateItemLabel", () => {
  test("names what each known gate guards and falls back for an unknown gate", () => {
    expect(gateItemLabel("interview_output")).toBe("a question");
    expect(gateItemLabel("research_input")).toBe("a search");
    expect(gateItemLabel("advice_output")).toBe("a suggestion");
    expect(gateItemLabel("new_gate")).toBe("an item");
  });
});
