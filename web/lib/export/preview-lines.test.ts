import { describe, expect, test } from "vitest";

import type { ExportPreview } from "@/lib/schemas/export";

import { missingLabels, newAndUpdated } from "./preview-lines";

describe("newAndUpdated", () => {
  test.each([
    [3, 1, "3 new · 1 updated"],
    [2, 0, "2 new"],
    [0, 4, "4 updated"],
    [0, 0, "nothing to save"],
  ])("%i new, %i updated is %s", (create, update, text) => {
    expect(newAndUpdated(create, update)).toBe(text);
  });
});

describe("missingLabels", () => {
  const base = { labels: { total: 2, items: [{ name: "web", exists: true }, { name: "server", exists: false }] } } as ExportPreview;

  test("counts labels Linear lacks", () => {
    expect(missingLabels(base)).toBe(1);
  });

  test("is null when Linear's labels could not be read", () => {
    const unknown = { labels: { total: 1, items: [{ name: "web", exists: null }] } } as ExportPreview;
    expect(missingLabels(unknown)).toBeNull();
  });
});
