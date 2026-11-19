"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { useForm, useWatch } from "react-hook-form";

import { ApprovalPrompt } from "@/components/chat/approval-prompt";
import { Composer, type ComposerAction } from "@/components/chat/composer";
import { ConversationLayout } from "@/components/chat/conversation-layout";
import { InterviewMessages } from "@/components/chat/interview-messages";
import { QuickReplies } from "@/components/chat/quick-replies";
import { RunNote, StartRunButton } from "@/components/chat/run-notice";
import { RunMessageBody } from "@/components/chat/run-message";
import { UserBubble } from "@/components/chat/user-bubble";
import { useAnswerActions } from "@/components/chat/use-answer-actions";
import { useRefreshIdea, useStartRunAction, useStopRunAction } from "@/components/chat/use-run-actions";
import { ResearchSection } from "@/components/research/research-section";
import { queryKeys } from "@/lib/api/queries/keys";
import { useInterview } from "@/lib/api/queries/use-interview";
import type { components } from "@/lib/api/schema";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";
import { RESEARCHER_NODE, finishedResearchSteps } from "@/lib/events/activity";
import { isActiveStatus } from "@/lib/events/reducer";
import { useRunEvents } from "@/lib/events/use-run-events";
import { buildInterviewThread } from "@/lib/interview/thread";
import { answerSchema, toAnswer, type AnswerFormValues } from "@/lib/schemas/answer";

type Idea = components["schemas"]["Idea"];
type RunView = components["schemas"]["RunView"];

const NO_ANSWER_PLACEHOLDER = "Nothing to answer right now";
const WORKING_PLACEHOLDER = "Metis is working…";
const APPROVAL_PLACEHOLDER = "Approve or reject above";
const ANSWER_PLACEHOLDER = "Type your answer";
const NOOP = () => undefined;

/** Refetches the interview turns and the research when the run produces something new for them. */
function useRefetchOnProgress(ideaId: string, newQuestion: string | null, researchDone: number) {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();
  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.interview(workspaceId, ideaId) });
  }, [queryClient, workspaceId, ideaId, newQuestion]);
  useEffect(() => {
    if (researchDone > 0) void queryClient.invalidateQueries({ queryKey: queryKeys.research(workspaceId, ideaId) });
  }, [queryClient, workspaceId, ideaId, researchDone]);
}

/** One run, live: the interview, the research, and a composer that answers the run's questions. */
export function RunConversation({ idea, run }: { idea: Idea; run: RunView }) {
  const refresh = useRefreshIdea(idea.id);
  // A refetch when the feed ends picks up the new stage, and a lost session redirects to sign-in.
  const { state, stream } = useRunEvents(run.id, run, () => void refresh());
  const { stop, stopping, error: stopError } = useStopRunAction(run.id);
  const { start, pending: starting, error: startError } = useStartRunAction(idea.id);
  const answers = useAnswerActions(run.id, () => void refresh());
  const turns = useInterview(idea.id);

  const interrupt = state.interrupt;
  const thread = useMemo(
    () => buildInterviewThread({ turns: turns.data ?? [], interrupt, sent: answers.sent }),
    [turns.data, interrupt, answers.sent],
  );
  const researchDone = finishedResearchSteps(state);
  useRefetchOnProgress(idea.id, interrupt?.kind === "question" ? interrupt.text : null, researchDone);

  const form = useForm<AnswerFormValues>({ resolver: zodResolver(answerSchema), defaultValues: { text: "" } });
  const text = useWatch({ control: form.control, name: "text" });

  const streamLost = stream === "failed";
  const active = isActiveStatus(state.status) && !streamLost;
  const awaiting = state.status === "awaiting_user" && !streamLost;
  // Wait for the turns: a replayed old question must not look pending before they say it is answered.
  const question = awaiting && !turns.isPending ? thread.pendingQuestion : null;
  const approval = awaiting && interrupt?.kind === "approval" && answers.choice === null ? interrupt : null;
  const canAnswer = question !== null && !answers.pending;
  const action: ComposerAction = question !== null || !active ? "send" : stopping ? "stopping" : "stop";

  const placeholder = question !== null
    ? ANSWER_PLACEHOLDER
    : approval
      ? APPROVAL_PLACEHOLDER
      : active
        ? WORKING_PLACEHOLDER
        : NO_ANSWER_PLACEHOLDER;

  const submit = form.handleSubmit((values) => {
    if (question === null) return;
    answers.answer(question, toAnswer(values));
    form.reset();
  });

  const composer = (
    <Composer
      label="Reply to Metis"
      textarea={{ ...form.register("text"), disabled: question === null, placeholder }}
      action={action}
      canSend={canAnswer && text.trim() !== ""}
      onSubmit={submit}
      onStop={stop}
      error={form.formState.errors.text?.message ?? answers.error ?? stopError ?? startError}
      above={
        question !== null ? (
          <QuickReplies
            disabled={answers.pending}
            onReply={(value) => answers.answer(question, value)}
            onStop={stop}
            stopping={stopping}
          />
        ) : null
      }
    />
  );

  return (
    <ConversationLayout
      idea={idea}
      scrollKey={[state, thread.messages.length]}
      interview={<InterviewMessages messages={thread.messages} />}
      composer={composer}
      body={
        <RunMessageBody
          state={state}
          streamLost={streamLost}
          retry={<StartRunButton label="Retry" pending={starting} onClick={start} />}
          research={<ResearchSection ideaId={idea.id} researchStarted={state.steps.some((step) => step.node === RESEARCHER_NODE)} />}
          approval={
            <>
              {approval ? <ApprovalPrompt interrupt={approval} disabled={answers.pending} onDecide={answers.decide} /> : null}
              {answers.choice ? <UserBubble text={answers.choice} /> : null}
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
        />
      }
      body={
        <div className="flex items-center gap-2">
          <RunNote>No run yet.</RunNote>
          <StartRunButton label="Start" pending={pending} onClick={start} />
        </div>
      }
    />
  );
}
