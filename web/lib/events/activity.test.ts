import { describe, expect, it } from "vitest";

import { finishedResearchSteps, runActivity } from "./activity";

const step = (node: string, done: boolean, tools: string[] = []) => ({ node, done, tools });

describe("runActivity", () => {
  it("names the running step", () => {
    expect(runActivity({ status: "running", steps: [step("interviewer", false)] })).toBe("Interviewer…");
  });

  it("shows Researching with the latest tool name", () => {
    const steps = [step("interviewer", true), step("researcher", false, ["web_search_exa", "web_fetch_exa"])];
    expect(runActivity({ status: "running", steps })).toBe("Researching… web_fetch_exa");
  });

  it("shows Researching alone before a tool call", () => {
    expect(runActivity({ status: "running", steps: [step("researcher", false)] })).toBe("Researching…");
  });

  it("falls back to Starting for a queued run and Thinking otherwise", () => {
    expect(runActivity({ status: "queued", steps: [] })).toBe("Starting…");
    expect(runActivity({ status: "running", steps: [step("interviewer", true)] })).toBe("Thinking…");
  });
});

describe("finishedResearchSteps", () => {
  it("counts only finished researcher steps", () => {
    const steps = [step("interviewer", true), step("researcher", true), step("researcher", false)];
    expect(finishedResearchSteps({ steps })).toBe(1);
  });
});
