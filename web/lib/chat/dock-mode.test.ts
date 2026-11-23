import { describe, expect, it } from "vitest";

import { dockMode } from "./dock-mode";

const withOptions = {
  kind: "question" as const,
  text: "Who?",
  options: [{ id: "o1", label: "A", recommended: false }],
};
const plain = { kind: "question" as const, text: "Who?" };
const base = { streamLost: false, question: null, typingOther: false, answered: false };

describe("dockMode", () => {
  it("is busy while the run is queued or running", () => {
    expect(dockMode({ ...base, status: "queued" })).toBe("busy");
    expect(dockMode({ ...base, status: "running" })).toBe("busy");
  });

  it("shows the picker for a question with options", () => {
    expect(dockMode({ ...base, status: "awaiting_user", question: withOptions })).toBe("choice");
  });

  it("shows the composer for a plain question", () => {
    expect(dockMode({ ...base, status: "awaiting_user", question: plain })).toBe("text");
  });

  it("shows the composer after Something else, until the user goes back", () => {
    expect(dockMode({ ...base, status: "awaiting_user", question: withOptions, typingOther: true })).toBe("text");
  });

  it("shows the composer for an idle or finished run and for a lost feed", () => {
    expect(dockMode({ ...base, status: "succeeded" })).toBe("text");
    expect(dockMode({ ...base, status: "failed" })).toBe("text");
    expect(dockMode({ ...base, status: "running", streamLost: true })).toBe("text");
  });

  it("stays busy between an answer and the run moving on, so the composer does not flash", () => {
    expect(dockMode({ ...base, status: "awaiting_user", question: withOptions, answered: true })).toBe("busy");
    expect(dockMode({ ...base, status: "awaiting_user", question: plain, answered: true })).toBe("busy");
  });

  it("shows the composer for an approval", () => {
    expect(dockMode({ ...base, status: "awaiting_user", question: { kind: "approval", text: "Create" } })).toBe("text");
  });
});
