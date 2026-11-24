"use client";

import type { useAnswerActions } from "@/components/chat/use-answer-actions";
import { hasOptions } from "@/lib/chat/choice";
import { dockMode, type DockMode } from "@/lib/chat/dock-mode";
import type { RunState } from "@/lib/events/reducer";
import type { AdviceInterrupt, ApprovalInterrupt, PhaseReviewInterrupt, SpecReviewInterrupt } from "@/lib/events/schemas";

type Answers = ReturnType<typeof useAnswerActions>;

type RunPromptsInput = {
  state: RunState;
  streamLost: boolean;
  /** True while the interview turns load: a replayed old question must not look pending yet. */
  turnsPending: boolean;
  /** The question the thread says the user can answer now, or null. */
  pendingQuestion: string | null;
  answers: Answers;
  /** The interrupt for which the user chose "Something else", or null. */
  otherSeq: number | null;
};

/** What the run waits for and which dock mode shows, derived from the run state and the user's answers. */
export function useRunPrompts({ state, streamLost, turnsPending, pendingQuestion, answers, otherSeq }: RunPromptsInput) {
  const { interrupt, interruptCount: seq } = state;
  const awaiting = state.status === "awaiting_user" && !streamLost;
  const question = awaiting && !turnsPending ? pendingQuestion : null;
  const pending = question !== null && interrupt?.kind === "question" ? interrupt : null;
  const offered = hasOptions(pending) ? pending : null;

  const decided = answers.decisions.some((decision) => decision.seq === seq);
  const adviceDecided = answers.adviceChoices.some((choice) => choice.seq === seq);
  const approval: ApprovalInterrupt | null =
    awaiting && interrupt?.kind === "approval" && !decided ? interrupt : null;
  const advice: AdviceInterrupt | null =
    awaiting && interrupt?.kind === "advice_decision" && !adviceDecided ? interrupt : null;
  const specReview: SpecReviewInterrupt | null = awaiting && interrupt?.kind === "spec_review" ? interrupt : null;
  const phaseReview: PhaseReviewInterrupt | null = awaiting && interrupt?.kind === "phase_review" ? interrupt : null;
  const answeredHere = answers.sent.some((entry) => entry.seq === seq) || decided || adviceDecided;

  const mode: DockMode = dockMode({
    status: state.status,
    streamLost,
    question: pending,
    typingOther: otherSeq === seq,
    answered: answeredHere,
  });
  return { awaiting, question, offered, approval, advice, specReview, phaseReview, answeredHere, mode };
}
