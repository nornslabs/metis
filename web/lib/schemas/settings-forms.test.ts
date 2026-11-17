import { describe, expect, it } from "vitest";

import { isValidBudget, isValidSteps, keysFormSchema, workspaceNameSchema } from "./settings-forms";

const valid = {
  llm: { base_url: "", model: "", value: "" },
  exa: { value: "" },
  run_budget_usd: "2.00",
  max_steps: "50",
};

function issuePaths(input: unknown): string[] {
  const result = keysFormSchema.safeParse(input);
  return result.success ? [] : result.error.issues.map((issue) => issue.path.join("."));
}

describe("keysFormSchema", () => {
  it("accepts untouched key inputs with valid limits", () => {
    expect(keysFormSchema.safeParse(valid).success).toBe(true);
  });

  it("requires a base URL and model when a new LLM key is entered", () => {
    const paths = issuePaths({ ...valid, llm: { base_url: "", model: " ", value: "sk-x" } });
    expect(paths).toEqual(["llm.base_url", "llm.model"]);
  });

  it("rejects a base URL that is not http(s)", () => {
    const llm = { base_url: "ftp://x.test", model: "m", value: "sk-x" };
    expect(issuePaths({ ...valid, llm })).toEqual(["llm.base_url"]);
  });

  it("accepts a complete LLM key", () => {
    const llm = { base_url: "https://api.openai.com/v1", model: "gpt-4.1", value: "sk-x" };
    expect(keysFormSchema.safeParse({ ...valid, llm }).success).toBe(true);
  });

  it("flags a bad budget and bad steps", () => {
    expect(issuePaths({ ...valid, run_budget_usd: "0", max_steps: "201" })).toEqual([
      "run_budget_usd",
      "max_steps",
    ]);
  });
});

describe("limits", () => {
  it.each(["0.01", "2", "100", "99.99"])("accepts budget %s", (value) => {
    expect(isValidBudget(value)).toBe(true);
  });

  it.each(["", "0", "-1", "100.01", "1.234", "abc", "1e2"])("rejects budget %s", (value) => {
    expect(isValidBudget(value)).toBe(false);
  });

  it.each(["1", "50", "200"])("accepts steps %s", (value) => {
    expect(isValidSteps(value)).toBe(true);
  });

  it.each(["0", "201", "1.5", "", "x"])("rejects steps %s", (value) => {
    expect(isValidSteps(value)).toBe(false);
  });
});

describe("workspaceNameSchema", () => {
  it("trims and rejects an empty name", () => {
    expect(workspaceNameSchema.safeParse({ name: "   " }).success).toBe(false);
    expect(workspaceNameSchema.parse({ name: " Acme " }).name).toBe("Acme");
  });
});
