"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";

import { Composer } from "@/components/chat/composer";
import { VoiceButton } from "@/components/chat/voice-button";
import { ConversationLayout } from "@/components/chat/conversation-layout";
import { Dock } from "@/components/chat/dock";
import { OutputCards } from "@/components/chat/output-cards";
import { RunApprovals } from "@/components/chat/run-approvals";
import { RunDock } from "@/components/chat/run-dock";
import { KeyGateNotice } from "@/components/chat/key-gate-notice";
import { InterviewMessages } from "@/components/chat/interview-messages";
import { QuickReplies } from "@/components/chat/quick-replies";
import { RunNote, StartRunButton } from "@/components/chat/run-notice";
import { RunMessageBody } from "@/components/chat/run-message";
import { UserBubble } from "@/components/chat/user-bubble";
import { useAnswerActions } from "@/components/chat/use-answer-actions";
import { useRunPrompts } from "@/components/chat/use-run-prompts";
import { useRefreshIdea, useStartRunAction, useStopRunAction } from "@/components/chat/use-run-actions";
import { queryKeys } from "@/lib/api/queries/keys";
import { getSTTClientProvider } from "@/lib/stt/config";
import { useKeyGate } from "@/lib/api/queries/use-key-gate";
import { useInterview } from "@/lib/api/queries/use-interview";
import { useResearch } from "@/lib/api/queries/use-research";
import { useSuggestions } from "@/lib/api/queries/use-suggestions";
import { useRunSync } from "@/lib/api/queries/use-run-sync";
import { toast } from "sonner";
import type { components } from "@/lib/api/schema";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";
import { pickedLabel } from "@/lib/chat/choice";
import { RESEARCHER_NODE, SCORER_NODE, finishedResearchSteps, runActivity } from "@/lib/events/activity";
import { isActiveStatus, isTerminalStatus } from "@/lib/events/reducer";
import { useRunEvents } from "@/lib/events/use-run-events";
import { stepCounter } from "@/lib/events/work-summary";
import { buildInterviewThread } from "@/lib/interview/thread";
import { answerSchema, pickValue, textValue, toAnswer, type AnswerFormValues } from "@/lib/schemas/answer";
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

  if (process.env.NODE_ENV === "development" && run.idea_id !== idea.id) {
    console.warn(
      `RunConversation: run.idea_id (${run.idea_id}) !== idea.id (${idea.id}) — possible cross-contamination`,
    );
  }

  useEffect(() => {
    if (process.env.NODE_ENV === "development") {
      console.log(`RunConversation mounted: run=${run.id} idea=${idea.id}`);
    }
    return () => {
      if (process.env.NODE_ENV === "development") {
        console.log(`RunConversation unmounted: run=${run.id} idea=${idea.id}`);
      }
    };
  }, [run.id, idea.id]);

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
  // "Something else" opens the composer for this interrupt only; the next question starts on options.
  const [otherSeq, setOtherSeq] = useState<number | null>(null);

  const streamLost = stream === "failed";
  const active = isActiveStatus(state.status) && !streamLost;
  const canContinue = isTerminalStatus(state.status);
  const canSubmitPrompt = canContinue && !starting;
  const { awaiting, question, offered, approval, advice, answeredHere, mode } = useRunPrompts({
    state,
    streamLost,
    turnsPending: turns.isPending,
    pendingQuestion: thread.pendingQuestion,
    answers,
    otherSeq,
  });
  const suggestions = useSuggestions(idea.id, advice !== null);
  const canAnswer = question !== null && !answers.pending;
  const researcherStarted = state.steps.some((step) => step.node === RESEARCHER_NODE);
  const sourceCount = useResearch(idea.id, researcherStarted).data?.items.length ?? null;

  const placeholder = composerPlaceholder({
    answering: question !== null,
    approval: approval !== null,
    advice: advice !== null,
    canContinue,
    starting,
    active,
  });

  const pick = (ids: readonly string[]) => {
    if (offered === null) return;
    answers.answer(seq, offered.text, { text: pickedLabel(offered.options, ids), value: pickValue(ids), picked: true });
  };

  const submit = form.handleSubmit((values) => {
    const answerText = toAnswer(values);
    if (question !== null) {
      // The text goes back into the box if the call fails, so nothing typed is lost.
      const value = textValue(answerText, offered !== null);
      answers.answer(seq, question, { text: answerText, value }, () => form.setValue("text", answerText));
      form.reset();
      return;
    }
    if (canContinue) {
      start(answerText, () => form.setValue("text", answerText));
      form.reset();
    }
  });

  const formError = form.formState.errors.text?.message ?? answers.error ?? stopError ?? startError;

  /** Voice input: transcribe the recorded blob and populate the text field. */
  const voice = (
    <VoiceButton
      onBlob={async (blob) => {
        try {
          const provider = getSTTClientProvider();
          const transcript = await provider.transcribe(blob);
          if (transcript.trim()) {
            form.setValue("text", transcript);
          } else {
            toast.error("Nothing heard. Try again.");
          }
        } catch {
          toast.error("Transcription failed. You can still type.");
        }
      }}
    />
  );

  const composer = (
    <Composer
      frameBand={false}
      label="Reply to Metis"
      textarea={{
        ...form.register("text"),
        disabled: question === null && !canSubmitPrompt,
        placeholder,
      }}
      action={question !== null || canContinue || !active ? "send" : stopping ? "stopping" : "stop"}
      canSend={(question !== null ? canAnswer : canSubmitPrompt) && text.trim() !== ""}
      onSubmit={submit}
      onStop={stop}
      onBack={offered !== null ? () => setOtherSeq(null) : undefined}
      error={formError}
      voice={voice}
      above={
        question !== null && offered === null ? (
          <QuickReplies
            disabled={answers.pending}
            onReply={(value) => answers.answer(seq, question, { text: value, value: textValue(value, false) })}
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

  const waiting = awaiting && !answeredHere;
  const owl = waiting ? "waiting" : mode === "busy" ? "working" : "idle";
  return (
    <ConversationLayout
      idea={idea}
      owl={owl}
      sentCount={answers.sent.length + answers.decisions.length + answers.adviceChoices.length}
      scrollKey={`${state.status}:${state.steps.length}:${state.text.length}:${thread.messages.length}:${answers.decisions.length}:${answers.adviceChoices.length}`}
      interview={
        <>
          <InterviewMessages messages={thread.messages} />
          {run.user_prompt ? <UserBubble text={run.user_prompt} /> : null}
        </>
      }
      composer={
        <RunDock
          mode={mode}
          working={{ label: runActivity(state), counter: stepCounter(state.steps), onStop: stop, stopping }}
          choice={{
            question: offered,
            disabled: answers.pending,
            onPick: pick,
            onOther: () => setOtherSeq(seq),
            onStop: stop,
            stopping,
          }}
          composer={composer}
          error={answers.error ?? stopError ?? startError}
        />
      }
      body={
        <RunMessageBody
          state={state}
          streamLost={streamLost}
          sourceCount={sourceCount}
          retry={<StartRunButton label="Retry" pending={starting} onClick={() => start()} blocked={gate.llmBlock !== null} />}
          outputs={
            <OutputCards
              ideaId={idea.id}
              runActive={active || state.status === "awaiting_user"}
              scoringStarted={state.steps.some((step) => step.node === SCORER_NODE)}
              researchStarted={researcherStarted}
            />
          }
          approval={
            <RunApprovals
              advice={advice}
              approval={approval}
              ideaText={idea.raw_text}
              accepted={acceptedFor(suggestions.data ?? [], advice?.scoreRunId ?? "")}
              adviceChoices={answers.adviceChoices}
              decisions={answers.decisions}
              disabled={answers.pending}
              onAdvise={(value, decision) => answers.advise(seq, value, decision)}
              onDecide={(approved) => answers.decide(seq, approved)}
            />
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
        <Dock mode="text">
          <Composer
            frameBand={false}
            label="Reply to Metis"
            textarea={{ disabled: true, placeholder: NO_ANSWER_PLACEHOLDER }}
            action="send"
            canSend={false}
            onSubmit={(event) => event.preventDefault()}
            onStop={NOOP}
            error={error}
            above={<KeyGateNotice gate={gate} includeExa />}
          />
        </Dock>
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
