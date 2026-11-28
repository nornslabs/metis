import { describe, expect, test } from "vitest";

import { splitAgentNotes } from "./brief";

describe("splitAgentNotes", () => {
  test("separates the Agent notes block from the brief", () => {
    const text = "## Goal\n\nBuild it.\n\n>>> Agent notes\n\nTouch the api.\n\n>>>";
    expect(splitAgentNotes(text)).toEqual({
      body: "## Goal\n\nBuild it.",
      notes: "Touch the api.",
    });
  });

  test("returns the whole brief when there is no block", () => {
    expect(splitAgentNotes("## Goal\n\nBuild it.")).toEqual({
      body: "## Goal\n\nBuild it.",
      notes: null,
    });
  });

  test("keeps text after the block and tolerates a missing close", () => {
    expect(splitAgentNotes(">>> Agent notes\n\nA\n\n>>>\n\n## After").body).toBe("## After");
    expect(splitAgentNotes("## Goal\n\n>>> Agent notes\n\nA").notes).toBe("A");
  });

  test("an empty block gives no notes", () => {
    expect(splitAgentNotes("Hi\n>>> Agent notes\n>>>").notes).toBeNull();
  });
});
