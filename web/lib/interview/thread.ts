import type { components } from "@/lib/api/schema";
import type { RunInterrupt } from "@/lib/events/schemas";

type InterviewTurn = components["schemas"]["InterviewTurn"];

/** One message of the interview: a question from Metis or the user's answer. */
export type InterviewMessage =
  | { readonly role: "agent"; readonly key: string; readonly text: string }
  | { readonly role: "user"; readonly key: string; readonly text: string };

/** An answer sent from this page that the turns list may not show yet (the worker saves it a moment later). */
export type SentAnswer = { readonly question: string; readonly text: string };

export type InterviewThreadInput = {
  readonly turns: readonly InterviewTurn[];
  /** The question the run waits on now, from the stream or the run view. */
  readonly interrupt: RunInterrupt | null;
  readonly sent: readonly SentAnswer[];
};

export type InterviewThread = {
  readonly messages: readonly InterviewMessage[];
  /** The question the user can answer now, or `null`. */
  readonly pendingQuestion: string | null;
};

function sentFor(sent: readonly SentAnswer[], question: string): string | undefined {
  return sent.findLast((answer) => answer.question === question)?.text;
}

/**
 * The questions Metis asked and the user's answers, in order. Only asked turns show (noted turns
 * were never put to the user). A question counts as answered by the server's answer or by one sent
 * from this page; the run's current question is added when the turns list does not hold it yet.
 */
export function buildInterviewThread({ turns, interrupt, sent }: InterviewThreadInput): InterviewThread {
  const messages: InterviewMessage[] = [];
  let pendingQuestion: string | null = null;
  const pendingText = interrupt?.kind === "question" ? interrupt.text : null;

  for (const turn of turns) {
    if (turn.source !== "asked") continue;
    messages.push({ role: "agent", key: `${turn.id}:q`, text: turn.question });
    const answer = turn.answer ?? sentFor(sent, turn.question);
    if (answer !== undefined && answer !== null) {
      messages.push({ role: "user", key: `${turn.id}:a`, text: answer });
    } else if (turn.question === pendingText) {
      pendingQuestion = turn.question;
    }
  }

  const listed = turns.some((turn) => turn.source === "asked" && turn.question === pendingText);
  if (pendingText !== null && !listed) {
    messages.push({ role: "agent", key: "pending:q", text: pendingText });
    const answer = sentFor(sent, pendingText);
    if (answer !== undefined) messages.push({ role: "user", key: "pending:a", text: answer });
    else pendingQuestion = pendingText;
  }

  return { messages, pendingQuestion };
}
