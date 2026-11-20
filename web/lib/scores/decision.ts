import { z } from "zod";

import type { components } from "@/lib/api/schema";

import type { Suggestion } from "./view";

export type AdviceResume = components["schemas"]["AdviceResume"];
export type AdviceDecision = AdviceResume["decision"];

/** The server's bounds on a revised idea text, and on how many accepted suggestions it takes. */
export const REVISED_TEXT_MIN = 10;
export const REVISED_TEXT_MAX = 10_000;
export const MAX_ACCEPTED_SUGGESTIONS = 5;

export const reviseSchema = z.object({
  text: z
    .string()
    .trim()
    .min(REVISED_TEXT_MIN, `Write at least ${REVISED_TEXT_MIN} characters.`)
    .max(REVISED_TEXT_MAX, `Keep it under ${REVISED_TEXT_MAX.toLocaleString("en-US")} characters.`),
});

export type ReviseFormValues = z.input<typeof reviseSchema>;

export const DECISION_LABELS: Readonly<Record<AdviceDecision, string>> = {
  revise: "Revise and rescore",
  continue: "Continue to spec",
  stop: "Stop here",
};

/** The accepted suggestions of one score run, the ones a revision will list (at most five). */
export function acceptedFor(suggestions: readonly Suggestion[], scoreRunId: string): readonly Suggestion[] {
  return suggestions
    .filter((entry) => entry.score_run_id === scoreRunId && entry.status === "accepted")
    .slice(0, MAX_ACCEPTED_SUGGESTIONS);
}

/** The resume value for `POST /v1/runs/{id}/resume`. */
export function buildResume(decision: AdviceDecision, revisedText?: string, accepted: readonly Suggestion[] = []): AdviceResume {
  if (decision !== "revise") return { decision, accepted_suggestion_ids: [] };
  return {
    decision,
    revised_text: revisedText?.trim() ?? "",
    accepted_suggestion_ids: accepted.map((entry) => entry.id),
  };
}
