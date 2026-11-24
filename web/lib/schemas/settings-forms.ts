import { z } from "zod";

export const MAX_BUDGET_USD = 100;
export const MIN_STEPS = 1;
export const MAX_STEPS = 200;

const MESSAGES = {
  baseUrl: "Enter a full URL, like https://api.openai.com/v1.",
  model: "Enter a model name.",
  secret: "Paste the key.",
  budget: `Enter an amount above 0 and up to ${MAX_BUDGET_USD}, with at most 2 decimals.`,
  steps: `Enter a whole number from ${MIN_STEPS} to ${MAX_STEPS}.`,
} as const;

const BUDGET_PATTERN = /^\d+(\.\d{1,2})?$/;
const STEPS_PATTERN = /^\d+$/;

function isHttpUrl(value: string): boolean {
  try {
    const { protocol } = new URL(value);
    return protocol === "https:" || protocol === "http:";
  } catch {
    return false;
  }
}

/** `0 < x <= 100`, 2 decimals at most. */
export function isValidBudget(value: string): boolean {
  const trimmed = value.trim();
  if (!BUDGET_PATTERN.test(trimmed)) return false;
  const amount = Number(trimmed);
  return amount > 0 && amount <= MAX_BUDGET_USD;
}

/** An integer from 1 to 200. */
export function isValidSteps(value: string): boolean {
  const trimmed = value.trim();
  if (!STEPS_PATTERN.test(trimmed)) return false;
  const steps = Number(trimmed);
  return steps >= MIN_STEPS && steps <= MAX_STEPS;
}

/**
 * The API keys tab as one form. Secret inputs are write-only: an empty `value` means "leave the
 * saved key alone". The LLM group needs a base URL and model whenever a new key is entered.
 * Numbers stay strings while editing; the submit handler converts them after validation.
 */
export const keysFormSchema = z
  .object({
    llm: z.object({ base_url: z.string(), model: z.string(), value: z.string() }),
    exa: z.object({ value: z.string() }),
    sarvam: z.object({ value: z.string() }),
    run_budget_usd: z.string(),
    max_steps: z.string(),
  })
  .superRefine((form, ctx) => {
    if (form.llm.value.trim() !== "") {
      if (!isHttpUrl(form.llm.base_url.trim())) {
        ctx.addIssue({ code: "custom", path: ["llm", "base_url"], message: MESSAGES.baseUrl });
      }
      if (form.llm.model.trim() === "") {
        ctx.addIssue({ code: "custom", path: ["llm", "model"], message: MESSAGES.model });
      }
    }
    if (!isValidBudget(form.run_budget_usd)) {
      ctx.addIssue({ code: "custom", path: ["run_budget_usd"], message: MESSAGES.budget });
    }
    if (!isValidSteps(form.max_steps)) {
      ctx.addIssue({ code: "custom", path: ["max_steps"], message: MESSAGES.steps });
    }
  });

export type KeysFormValues = z.infer<typeof keysFormSchema>;

export const workspaceNameSchema = z.object({
  name: z.string().trim().min(1, "Enter a name.").max(80, "Use 80 characters or fewer."),
});

export type WorkspaceNameValues = z.infer<typeof workspaceNameSchema>;
