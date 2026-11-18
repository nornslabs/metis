import { describe, expect, test } from "vitest";

import { nodeLabel, stageLabel } from "./labels";

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
