"use client";

import { useState } from "react";

import { ApiError, describeError, fieldErrors } from "@/lib/api/errors";
import { useResumeRun } from "@/lib/api/mutations/use-resume-run";
import type { SentAnswer } from "@/lib/interview/thread";
import type { QuestionResumeValue } from "@/lib/schemas/answer";
import { DECISION_LABELS, type AdviceDecision, type AdviceResume } from "@/lib/scores/decision";

const INVALID_STATE = "run.invalid_state";
const MOVED_ON_MESSAGE = "This run already moved on.";
const VALUE_FIELD = "value";

/** The user's choice on one approval interrupt (`seq` is `RunState.interruptCount` when it was made). */
export type Decision = { readonly seq: number; readonly approved: boolean };

function messageFor(caught: unknown): string {
  if (caught instanceof ApiError) {
    if (caught.code === INVALID_STATE) return MOVED_ON_MESSAGE;
    // A 422 names the field (`body.value`): show its message under the composer.
    const field = fieldErrors(caught).find(({ name }) => name === VALUE_FIELD);
    if (field) return field.error.message;
  }
  return describeError(caught);
}

/** One answer to a question: what the thread shows, what the server gets, and whether it was a pick. */
export type AnsweredQuestion = {
  readonly text: string;
  readonly value: QuestionResumeValue;
  readonly picked?: boolean;
};

/** The user's choice on one advice decision, shown in the thread. */
export type AdviceChoice = { readonly seq: number; readonly label: string };

/**
 * Answers a question or an approval. Each answer is tied to the interrupt it answers (`seq`), so a
 * repeated question or a second approval is never mistaken for an answered one. The answer shows at
 * once and is taken back if the call fails; `409 run.invalid_state` (answered elsewhere, or the run
 * ended) refetches the run.
 */
export function useAnswerActions(runId: string, onMovedOn: () => void) {
  const resume = useResumeRun();
  const [sent, setSent] = useState<readonly SentAnswer[]>([]);
  const [decisions, setDecisions] = useState<readonly Decision[]>([]);
  const [adviceChoices, setAdviceChoices] = useState<readonly AdviceChoice[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fail = (caught: unknown, undo: () => void) => {
    undo();
    setError(messageFor(caught));
    if (caught instanceof ApiError && caught.code === INVALID_STATE) onMovedOn();
  };

  /**
   * `text` is what the thread shows as the user's answer; `value` is what the server gets (a pick
   * sends ids, the thread shows their labels). `onRejected` runs when the call fails, e.g. to put
   * the typed text back.
   */
  const answer = (seq: number, question: string, answered: AnsweredQuestion, onRejected?: () => void) => {
    setError(null);
    const entry: SentAnswer = { seq, question, text: answered.text, ...(answered.picked && { picked: true }) };
    setSent((current) => [...current, entry]);
    resume.mutate(
      { runId, value: answered.value },
      {
        onError: (caught) =>
          fail(caught, () => {
            setSent((current) => current.filter((item) => item !== entry));
            onRejected?.();
          }),
      },
    );
  };

  const decide = (seq: number, approved: boolean) => {
    setError(null);
    const decision: Decision = { seq, approved };
    setDecisions((current) => [...current, decision]);
    resume.mutate(
      { runId, value: approved },
      { onError: (caught) => fail(caught, () => setDecisions((current) => current.filter((item) => item !== decision))) },
    );
  };

  const advise = (seq: number, value: AdviceResume, decision: AdviceDecision) => {
    setError(null);
    const choice: AdviceChoice = { seq, label: DECISION_LABELS[decision] };
    setAdviceChoices((current) => [...current, choice]);
    resume.mutate(
      { runId, value },
      { onError: (caught) => fail(caught, () => setAdviceChoices((current) => current.filter((item) => item !== choice))) },
    );
  };

  return { answer, decide, advise, sent, decisions, adviceChoices, pending: resume.isPending, error };
}
