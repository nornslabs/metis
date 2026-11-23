import type { components } from "@/lib/api/schema";
import type { RunInterrupt } from "@/lib/events/schemas";

type InterviewTurn = components["schemas"]["InterviewTurn"];

/** One message of the interview: a question from Metis or the user's answer. */
export type InterviewMessage =
  | { readonly role: "agent"; readonly key: string; readonly text: string }
  | { readonly role: "user"; readonly key: string; readonly text: string; readonly picked?: boolean };

/**
 * An answer sent from this page that the turns list may not show yet (the worker saves it a moment
 * later). `seq` is the interrupt it answered (`RunState.interruptCount` when it was sent), so a
 * question asked twice is told apart by its interrupt, not by its text.
 */
export type SentAnswer = {
  readonly seq: number;
  readonly question: string;
  readonly text: string;
  /** True when the answer was picked from options (its bubble shows a check). */
  readonly picked?: boolean;
};

export type InterviewThreadInput = {
  readonly turns: readonly InterviewTurn[];
  /** The question the run waits on now, from the stream or the run view. */
  readonly interrupt: RunInterrupt | null;
  /** `RunState.interruptCount`: which interrupt `interrupt` is. */
  readonly interruptSeq: number;
  readonly sent: readonly SentAnswer[];
};

export type InterviewThread = {
  readonly messages: readonly InterviewMessage[];
  /** The question the user can answer now, or `null`. */
  readonly pendingQuestion: string | null;
};

function sentAnswer(sent: readonly SentAnswer[], question: string, accepts: (seq: number) => boolean) {
  return sent.findLast((entry) => entry.question === question && accepts(entry.seq))?.text;
}

/** True when this page sent `text` for `question` as a pick (the saved answer carries no such mark). */
function wasPicked(sent: readonly SentAnswer[], question: string, text: string): boolean {
  return sent.some((entry) => entry.picked === true && entry.question === question && entry.text === text);
}

function userMessage(key: string, question: string, text: string, sent: readonly SentAnswer[]): InterviewMessage {
  return wasPicked(sent, question, text) ? { role: "user", key, text, picked: true } : { role: "user", key, text };
}

/**
 * The questions Metis asked and the user's answers, in order. Only asked turns show (noted turns
 * were never put to the user). The run's current question is the newest open turn with its text;
 * it counts as answered by an answer sent for this interrupt. Older open turns take an answer sent
 * for an earlier interrupt. The current question is added when the turns list does not hold it yet.
 */
export function buildInterviewThread({ turns, interrupt, interruptSeq, sent }: InterviewThreadInput): InterviewThread {
  const asked = turns.filter((turn) => turn.source === "asked");
  const pendingText = interrupt?.kind === "question" ? interrupt.text : null;
  const pendingIndex =
    pendingText === null ? -1 : asked.findLastIndex((turn) => turn.answer === null && turn.question === pendingText);
  // With a pending question, an answer sent for this interrupt belongs to it, not to an older turn.
  const olderLimit = pendingText === null ? interruptSeq : interruptSeq - 1;
  const answeredNow = (question: string) => sentAnswer(sent, question, (seq) => seq === interruptSeq);

  const messages: InterviewMessage[] = [];
  let pendingQuestion: string | null = null;

  asked.forEach((turn, index) => {
    messages.push({ role: "agent", key: `${turn.id}:q`, text: turn.question });
    const isPending = index === pendingIndex;
    const answer = turn.answer ?? (isPending ? answeredNow(turn.question) : sentAnswer(sent, turn.question, (seq) => seq <= olderLimit));
    if (answer !== undefined && answer !== null) messages.push(userMessage(`${turn.id}:a`, turn.question, answer, sent));
    else if (isPending) pendingQuestion = turn.question;
  });

  if (pendingText !== null && pendingIndex === -1) {
    const answer = answeredNow(pendingText);
    const alreadyShown = answer !== undefined && asked.some((turn) => turn.question === pendingText);
    if (!alreadyShown) {
      messages.push({ role: "agent", key: "pending:q", text: pendingText });
      if (answer !== undefined) messages.push(userMessage("pending:a", pendingText, answer, sent));
      else pendingQuestion = pendingText;
    }
  }

  return { messages, pendingQuestion };
}
