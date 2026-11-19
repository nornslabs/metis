"use client";

import { useState } from "react";

import { ApiError, describeError } from "@/lib/api/errors";
import { useResumeRun } from "@/lib/api/mutations/use-resume-run";
import type { SentAnswer } from "@/lib/interview/thread";

const INVALID_STATE = "run.invalid_state";
const MOVED_ON_MESSAGE = "This run already moved on.";

/**
 * Answers a question or an approval. The answer shows at once (`sent`, `choice`) and is taken back
 * if the call fails; `409 run.invalid_state` (answered elsewhere, or the run ended) refetches the run.
 */
export function useAnswerActions(runId: string, onMovedOn: () => void) {
  const resume = useResumeRun();
  const [sent, setSent] = useState<readonly SentAnswer[]>([]);
  const [choice, setChoice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fail = (caught: unknown, undo: () => void) => {
    undo();
    const movedOn = caught instanceof ApiError && caught.code === INVALID_STATE;
    setError(movedOn ? MOVED_ON_MESSAGE : describeError(caught));
    if (movedOn) onMovedOn();
  };

  const answer = (question: string, text: string) => {
    setError(null);
    const entry: SentAnswer = { question, text };
    setSent((current) => [...current, entry]);
    resume.mutate(
      { runId, value: text },
      { onError: (caught) => fail(caught, () => setSent((current) => current.filter((item) => item !== entry))) },
    );
  };

  const decide = (approved: boolean) => {
    setError(null);
    setChoice(approved ? "Approved" : "Rejected");
    resume.mutate({ runId, value: approved }, { onError: (caught) => fail(caught, () => setChoice(null)) });
  };

  return { answer, decide, sent, choice, pending: resume.isPending, error };
}
