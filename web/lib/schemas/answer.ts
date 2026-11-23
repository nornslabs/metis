import { z } from "zod";

// Matches the server's resume check for a question (`check_resume_value`): trimmed, 1–10,000 characters.
export const ANSWER_MAX = 10_000;

/** What a quick reply sends: the server reads these as "skip this topic" and "end the interview". */
export const QUICK_REPLIES = [
  { label: "Skip", value: "skip" },
  { label: "That's enough", value: "that's enough" },
] as const;

export const answerSchema = z.object({
  text: z
    .string()
    .trim()
    .min(1, "Type an answer first.")
    .max(ANSWER_MAX, `Keep your answer under ${ANSWER_MAX.toLocaleString("en-US")} characters.`),
});

export type AnswerFormValues = z.input<typeof answerSchema>;

/** The `POST /v1/runs/{id}/resume` text for valid form values. */
export function toAnswer(values: AnswerFormValues): string {
  return values.text.trim();
}

/** What `POST /v1/runs/{id}/resume` takes for a question: typed text, a typed "Something else", or picks. */
export type QuestionResumeValue = string | { option_ids: string[]; text?: string };

/** The value for typed text: a plain string for a plain question, `{text}` when the question offered options. */
export function textValue(text: string, offeredOptions: boolean): QuestionResumeValue {
  return offeredOptions ? { option_ids: [], text } : text;
}

/** The value for picked options; the server turns the ids into the saved labels. */
export function pickValue(optionIds: readonly string[]): QuestionResumeValue {
  return { option_ids: [...optionIds] };
}
