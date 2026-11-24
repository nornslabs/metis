import type { InterviewMessage } from "./thread";

/** How many questions the messages hold: each starts at an agent message. */
export function countQuestions(messages: readonly InterviewMessage[]): number {
  return messages.filter((message) => message.role === "agent").length;
}

export type SplitSegments = {
  /** `leads[i]` is the text shown just before question i (after the answer to question i - 1). */
  readonly leads: readonly string[];
  /** Everything after the last question that has a row: the run's own message. */
  readonly tail: string;
};

/**
 * Pairs the run's text segments with its question rows. A segment with no row to sit before (a
 * question that was re-asked and saved once) joins the tail, so no text is lost.
 */
export function splitSegments(segments: readonly string[], questions: number): SplitSegments {
  return {
    leads: segments.slice(0, questions),
    tail: segments
      .slice(questions)
      .filter((segment) => segment !== "")
      .join("\n\n"),
  };
}
