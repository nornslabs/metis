import { describe, expect, it } from "vitest";

import { footerStatus } from "./footer-status";

const draft = { status: "draft", version: 3 } as const;

describe("footerStatus", () => {
  it("shows the version before any save", () => {
    expect(footerStatus(draft, { status: "idle", saved: 0 })).toEqual({ text: "Plan v3", tone: "muted" });
  });

  it("follows the save: saving, saved, failed, conflict", () => {
    expect(footerStatus(draft, { status: "saving", saved: 0 }).text).toBe("Saving…");
    expect(footerStatus(draft, { status: "idle", saved: 2 })).toEqual({ text: "Saved · v3", tone: "success" });
    expect(footerStatus(draft, { status: "failed", saved: 2 }).tone).toBe("destructive");
    expect(footerStatus(draft, { status: "conflict", saved: 2 }).text).toBe("Plan changed elsewhere");
  });

  it("says ready whatever the editor state is", () => {
    expect(footerStatus({ status: "ready", version: 4 }, { status: "failed", saved: 1 }).text).toBe("Plan ready · v4");
  });
});
