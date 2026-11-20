"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { useForm, useWatch } from "react-hook-form";

import { AdviceDecision } from "@/components/chat/advice-decision";
import { ApprovalPrompt } from "@/components/chat/approval-prompt";
import { Composer, type ComposerAction } from "@/components/chat/composer";
import { ConversationLayout } from "@/components/chat/conversation-layout";
import { KeyGateNotice } from "@/components/chat/key-gate-notice";
import { InterviewMessages } from "@/components/chat/interview-messages";
import { QuickReplies } from "@/components/chat/quick-replies";
import { RunNote, StartRunButton } from "@/components/chat/run-notice";
import { RunMessageBody } from "@/components/chat/run-message";
import { UserBubble } from "@/components/chat/user-bubble";
import { useAnswerActions } from "@/components/chat/use-answer-actions";
import { useRefreshIdea, useStartRunAction, useStopRunAction } from "@/components/chat/use-run-actions";
import { ResearchSection } from "@/components/research/research-section";
import { ScoreSection } from "@/components/score/score-section";
import { queryKeys } from "@/lib/api/queries/keys";
import { useKeyGate } from "@/lib/api/queries/use-key-gate";
import { useInterview } from "@/lib/api/queries/use-interview";
import { useSuggestions } from "@/lib/api/queries/use-suggestions";
import { useRunSync } from "@/lib/api/queries/use-run-sync";
import type { components } from "@/lib/api/schema";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";
import { RESEARCHER_NODE, SCORER_NODE, finishedResearchSteps } from "@/lib/events/activity";
import { isActiveStatus, isTerminalStatus } from "@/lib/events/reducer";
import { useRunEvents } from "@/lib/events/use-run-events";
import { buildInterviewThread } from "@/lib/interview/thread";
import { answerSchema, toAnswer, type AnswerFormValues } from "@/lib/schemas/answer";
import { acceptedFor } from "@/lib/scores/decision";

type Idea = components["schemas"]["Idea"];
type RunView = components["schemas"]["RunView"];

const NO_ANSWER_PLACEHOLDER = "Nothing to answer right now";
const WORKING_PLACEHOLDER = "Metis is working…";
const APPROVAL_PLACEHOLDER = "Approve or reject above";
const ADVICE_PLACEHOLDER = "Decide above";
const ANSWER_PLACEHOLDER = "Type your answer";
const NOOP = () => undefined;

/** Refetches the interview turns, the research and the scores when the run produces something new for them. */
function useRefetchOnProgress(ideaId: string, interruptCount: number, researchDone: number, scoreRunId: string | null) {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();
  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.interview(workspaceId, ideaId) });
  }, [queryClient, workspaceId, ideaId, interruptCount]);
  useEffect(() => {
    if (researchDone > 0) void queryClient.invalidateQueries({ queryKey: queryKeys.research(workspaceId, ideaId) });
  }, [queryClient, workspaceId, ideaId, researchDone]);
  // A new score run: the card, the history and the suggestions (the Advisor saves them just before).
  useEffect(() => {
    if (scoreRunId === null) return;
    void queryClient.invalidateQueries({ queryKey: queryKeys.latestScore(workspaceId, ideaId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.scoreHistory(workspaceId, ideaId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.suggestions(workspaceId, ideaId) });
  }, [queryClient, workspaceId, ideaId, scoreRunId]);
}

type PlaceholderInput = {
  answering: boolean;
  approval: boolean;
  advice: boolean;
  canContinue: boolean;
  starting: boolean;
  active: boolean;
};

/** What the composer says: what it takes now, or why it waits. */
function composerPlaceholder({ answering, approval, advice, canContinue, starting, active }: PlaceholderInput): string {
  if (answering) return ANSWER_PLACEHOLDER;
  if (approval) return APPROVAL_PLACEHOLDER;
  if (advice) return ADVICE_PLACEHOLDER;
  if (canContinue) return starting ? "Sending…" : "Continue this chat…";
  return active ? WORKING_PLACEHOLDER : NO_ANSWER_PLACEHOLDER;
}

/** One run, live: the interview, the research, and a composer that answers the run's questions. */
export function RunConversation({ idea, run }: { idea: Idea; run: RunView }) {
  const refresh = useRefreshIdea(idea.id);
  // A refetch when the feed ends picks up the new stage, and a lost session redirects to sign-in.
  const { state, stream, sync } = useRunEvents(run.id, run, () => void refresh());
  const { stop, stopping, error: stopError } = useStopRunAction(run.id);
  const { start, pending: starting, error: startError } = useStartRunAction(idea.id);
  const answers = useAnswerActions(run.id, () => void refresh());
  const turns = useInterview(idea.id);
  const gate = useKeyGate();

  // The stream is primary; this poll only catches a pause or finish it did not deliver.
  useRunSync(run.id, state.status === "queued" || state.status === "running", sync);

  const interrupt = state.interrupt;
  const seq = state.interruptCount;
  const thread = useMemo(
    () => buildInterviewThread({ turns: turns.data ?? [], interrupt, interruptSeq: seq, sent: answers.sent }),
    [turns.data, interrupt, seq, answers.sent],
  );
  const researchDone = finishedResearchSteps(state);
  useRefetchOnProgress(idea.id, seq, researchDone, state.scoreRunId);

  const form = useForm<AnswerFormValues>({ resolver: zodResolver(answerSchema), defaultValues: { text: "" } });
  const text = useWatch({ control: form.control, name: "text" });

  const streamLost = stream === "failed";
  const active = isActiveStatus(state.status) && !streamLost;
  const awaiting = state.status === "awaiting_user" && !streamLost;
  const canContinue = isTerminalStatus(state.status);
  const canSubmitPrompt = canContinue && !starting;
  // Wait for the turns: a replayed old question must not look pending before they say it is answered.
  const question = awaiting && !turns.isPending ? thread.pendingQuestion : null;
  const decided = answers.decisions.some((decision) => decision.seq === seq);
  const approval = awaiting && interrupt?.kind === "approval" && !decided ? interrupt : null;
  const adviceDecided = answers.adviceChoices.some((choice) => choice.seq === seq);
  const advice = awaiting && interrupt?.kind === "advice_decision" && !adviceDecided ? interrupt : null;
  const suggestions = useSuggestions(idea.id, advice !== null);
  const canAnswer = question !== null && !answers.pending;
  const action: ComposerAction =
    question !== null || canContinue || !active ? "send" : stopping ? "stopping" : "stop";

  const placeholder = composerPlaceholder({
    answering: question !== null,
    approval: approval !== null,
    advice: advice !== null,
    canContinue,
    starting,
    active,
  });

  const submit = form.handleSubmit((values) => {
    const answerText = toAnswer(values);
    if (question !== null) {
      // The text goes back into the box if the call fails, so nothing typed is lost.
      answers.answer(seq, question, answerText, () => form.setValue("text", answerText));
      form.reset();
      return;
    }
    if (canContinue) {
      start(answerText, () => form.setValue("text", answerText));
      form.reset();
    }
  });

  const composer = (
    <Composer
      label="Reply to Metis"
      textarea={{
        ...form.register("text"),
        disabled: question === null && !canSubmitPrompt,
        placeholder,
      }}
      action={action}
      canSend={(question !== null ? canAnswer : canSubmitPrompt) && text.trim() !== ""}
      onSubmit={submit}
      onStop={stop}
      error={form.formState.errors.text?.message ?? answers.error ?? stopError ?? startError}
      above={
        question !== null ? (
          <QuickReplies
            disabled={answers.pending}
            onReply={(value) => answers.answer(seq, question, value)}
            onStop={stop}
            stopping={stopping}
          />
          ) : canContinue ? (
            // Retry or continue starts a new run, so the LLM-key block applies here too.
          <KeyGateNotice gate={gate} includeExa={false} />
        ) : null
      }
    />
  );

  return (
    <ConversationLayout
      idea={idea}
      scrollKey={`${state.status}:${state.steps.length}:${state.text.length}:${thread.messages.length}:${answers.decisions.length}:${answers.adviceChoices.length}`}
      interview={
        <>
          <InterviewMessages messages={thread.messages} />
          {run.user_prompt ? <UserBubble text={run.user_prompt} /> : null}
        </>
      }
      composer={composer}
      body={
        <RunMessageBody
          state={state}
          streamLost={streamLost}
          retry={<StartRunButton label="Retry" pending={starting} onClick={() => start()} blocked={gate.llmBlock !== null} />}
          research={<ResearchSection ideaId={idea.id} researchStarted={state.steps.some((step) => step.node === RESEARCHER_NODE)} />}
          score={
            <ScoreSection
              ideaId={idea.id}
              runActive={active || state.status === "awaiting_user"}
              scoringStarted={state.steps.some((step) => step.node === SCORER_NODE)}
            />
          }
          approval={
            <>
              {advice ? (
                <AdviceDecision
                  interrupt={advice}
                  ideaText={idea.raw_text}
                  accepted={acceptedFor(suggestions.data ?? [], advice.scoreRunId)}
                  disabled={answers.pending}
                  onDecide={(value, decision) => answers.advise(seq, value, decision)}
                />
              ) : null}
              {answers.adviceChoices.map((choice) => (
                <UserBubble key={choice.seq} text={choice.label} />
              ))}
              {approval ? (
                <ApprovalPrompt interrupt={approval} disabled={answers.pending} onDecide={(approved) => answers.decide(seq, approved)} />
              ) : null}
              {answers.decisions.map((decision) => (
                <UserBubble key={decision.seq} text={decision.approved ? "Approved" : "Rejected"} />
              ))}
            </>
          }
        />
      }
    />
  );
}

/** An idea with no run yet: Start begins the first one. */
export function NoRunConversation({ idea }: { idea: Idea }) {
  const { start, pending, error } = useStartRunAction(idea.id);
  const gate = useKeyGate();
  return (
    <ConversationLayout
      idea={idea}
      composer={
        <Composer
          label="Reply to Metis"
          textarea={{ disabled: true, placeholder: NO_ANSWER_PLACEHOLDER }}
          action="send"
          canSend={false}
          onSubmit={(event) => event.preventDefault()}
          onStop={NOOP}
          error={error}
          above={<KeyGateNotice gate={gate} includeExa />}
        />
      }
      body={
        <div className="flex items-center gap-2">
          <RunNote>No run yet.</RunNote>
          <StartRunButton label="Start" pending={pending} onClick={() => start()} blocked={gate.llmBlock !== null} />
        </div>
      }
    />
  );
}
