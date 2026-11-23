import type { QuestionInterrupt, QuestionOption } from "@/lib/events/schemas";

/** How the server joins several picked labels into one saved answer (`check_resume_value`). */
export const LABEL_SEPARATOR = "; ";

/** Keys 1–9 pick the option at that position; 0 opens "Something else". */
export const MAX_KEYED_OPTIONS = 9;
export const OTHER_KEY = "0";

/** What a key press means for a question with options. */
export type KeyChoice =
  | { readonly kind: "option"; readonly option: QuestionOption }
  | { readonly kind: "other" }
  | null;

/** True when the question offers options to pick from (otherwise it is answered with text). */
export function hasOptions(question: QuestionInterrupt | null): question is QuestionInterrupt & {
  options: readonly QuestionOption[];
} {
  return question !== null && (question.options?.length ?? 0) > 0;
}

/** The options a multi-choice question starts with checked: the recommended ones. */
export function recommendedIds(options: readonly QuestionOption[]): readonly string[] {
  return options.filter((option) => option.recommended).map((option) => option.id);
}

/** A new list with `id` added, or removed when it was there. */
export function toggleId(checked: readonly string[], id: string): readonly string[] {
  return checked.includes(id) ? checked.filter((current) => current !== id) : [...checked, id];
}

/** Maps a key to an option or "Something else"; `null` for any other key or a missing option. */
export function keyChoice(key: string, options: readonly QuestionOption[], allowFreeText: boolean): KeyChoice {
  if (key === OTHER_KEY) return allowFreeText ? { kind: "other" } : null;
  if (!/^[1-9]$/.test(key)) return null;
  const option = options.slice(0, MAX_KEYED_OPTIONS)[Number(key) - 1];
  return option ? { kind: "option", option } : null;
}

/** The picked labels in option order, joined as the server saves them (what the user's bubble shows). */
export function pickedLabel(options: readonly QuestionOption[], ids: readonly string[]): string {
  return options
    .filter((option) => ids.includes(option.id))
    .map((option) => option.label)
    .join(LABEL_SEPARATOR);
}

/** "Question 2 of 5", "Question 2" when the total is unknown, else "Pick an answer". */
export function questionHeading(index: number | undefined, total: number | undefined): string {
  if (index === undefined) return "Pick an answer";
  return total === undefined ? `Question ${index}` : `Question ${index} of ${Math.max(index, total)}`;
}

/** The key hint under the heading: "1–4 to pick", "1 to pick" or, for several, "1–4 to toggle · Enter to continue". */
export function keyHint(optionCount: number, multi: boolean): string {
  const keyed = Math.min(optionCount, MAX_KEYED_OPTIONS);
  const range = keyed === 1 ? "1" : `1–${keyed}`;
  return multi ? `${range} to toggle · Enter to continue` : `${range} to pick`;
}
