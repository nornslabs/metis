import { describe, expect, test } from "vitest";

import { fileNameFrom } from "./export-markdown";

describe("fileNameFrom", () => {
  test("reads the quoted file name", () => {
    expect(fileNameFrom('attachment; filename="metis-habit-tracker-plan.md"')).toBe("metis-habit-tracker-plan.md");
  });

  test("falls back when the header is missing or has no name", () => {
    expect(fileNameFrom(null)).toBe("metis-plan.md");
    expect(fileNameFrom("attachment")).toBe("metis-plan.md");
  });

  test("never takes a path out of the header", () => {
    expect(fileNameFrom('attachment; filename="../x.md"')).toBe("metis-plan.md");
  });
});
