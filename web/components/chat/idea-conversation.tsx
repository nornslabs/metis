"use client";

import Link from "next/link";
import { useEffect, useRef, type ReactNode } from "react";

import { AgentMessage } from "@/components/chat/agent-message";
import { Composer, type ComposerAction } from "@/components/chat/composer";
import { RunNote, StartRunButton } from "@/components/chat/run-notice";
import { RunMessageBody } from "@/components/chat/run-message";
import { Thread } from "@/components/chat/thread";
import { useRefreshIdea, useStartRunAction, useStopRunAction } from "@/components/chat/use-run-actions";
import { UserBubble } from "@/components/chat/user-bubble";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, describeError } from "@/lib/api/errors";
import { useIdea } from "@/lib/api/queries/use-idea";
import { useLatestRun } from "@/lib/api/queries/use-latest-run";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";
import type { components } from "@/lib/api/schema";
import { stageLabel } from "@/lib/events/labels";
import { isActiveStatus } from "@/lib/events/reducer";
import { useRunEvents } from "@/lib/events/use-run-events";

type Idea = components["schemas"]["Idea"];
type RunView = components["schemas"]["RunView"];

const NO_ANSWER_PLACEHOLDER = "Answering comes soon";
// Follow new content only when the reader is this close to the bottom (after it rendered).
const STICK_THRESHOLD_PX = 480;

/** Keeps the newest content in view while the reader is already at the bottom. */
function useStickToBottom(dependency: unknown) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const end = endRef.current;
    const scroller = end?.closest("[data-scroll]");
    if (!end || !scroller) return;
    const distance = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    if (distance < STICK_THRESHOLD_PX) end.scrollIntoView({ block: "end" });
  }, [dependency]);
  return endRef;
}

interface ConversationLayoutProps {
  idea: Idea;
  /** The agent message's content. */
  body: ReactNode;
  action: ComposerAction;
  onStop?: () => void;
  composerError?: string | null;
  scrollKey?: unknown;
}

function ConversationLayout({ idea, body, action, onStop, composerError, scrollKey }: ConversationLayoutProps) {
  const endRef = useStickToBottom(scrollKey);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div data-scroll className="min-h-0 flex-1 overflow-y-auto">
        <Thread>
          <UserBubble text={idea.raw_text} />
          <AgentMessage
            aside={
              <Badge variant="outline" className="h-badge px-1.5 text-meta font-normal" aria-label={`Stage: ${stageLabel(idea.stage)}`}>
                {stageLabel(idea.stage)}
              </Badge>
            }
          >
            {body}
          </AgentMessage>
          <div ref={endRef} />
        </Thread>
      </div>
      <Composer
        label="Reply to Metis"
        textarea={{ disabled: true, placeholder: NO_ANSWER_PLACEHOLDER }}
        action={action}
        canSend={false}
        onSubmit={(event) => event.preventDefault()}
        onStop={onStop}
        error={composerError}
      />
    </div>
  );
}

function RunConversation({ idea, run }: { idea: Idea; run: RunView }) {
  const refresh = useRefreshIdea(idea.id);
  // A refetch when the feed ends picks up the new stage, and a lost session redirects to sign-in.
  const { state, stream } = useRunEvents(run.id, run, () => void refresh());
  const { stop, stopping, error: stopError } = useStopRunAction(run.id);
  const { start, pending, error: startError } = useStartRunAction(idea.id);
  const streamLost = stream === "failed";
  const active = isActiveStatus(state.status) && !streamLost;
  const action: ComposerAction = !active ? "send" : stopping ? "stopping" : "stop";

  return (
    <ConversationLayout
      idea={idea}
      action={action}
      onStop={stop}
      composerError={stopError ?? startError}
      scrollKey={state}
      body={
        <RunMessageBody
          state={state}
          streamLost={streamLost}
          retry={<StartRunButton label="Retry" pending={pending} onClick={start} />}
        />
      }
    />
  );
}

function NoRunConversation({ idea }: { idea: Idea }) {
  const { start, pending, error } = useStartRunAction(idea.id);
  return (
    <ConversationLayout
      idea={idea}
      action="send"
      composerError={error}
      body={
        <div className="flex items-center gap-2">
          <RunNote>No run yet.</RunNote>
          <StartRunButton label="Start" pending={pending} onClick={start} />
        </div>
      }
    />
  );
}

export function ConversationSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading idea" className="mx-auto flex w-(--col) flex-col gap-3 px-5 pt-4 max-guides:px-4">
      <Skeleton className="ml-auto h-8 w-1/2" />
      <Skeleton className="h-3 w-1/3" />
      <Skeleton className="h-16 w-full" />
    </div>
  );
}

function ConversationProblem({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-1 flex-col items-center justify-center gap-1.5 px-5 text-center">
      <h1 className="text-title font-semibold">{title}</h1>
      <p className="max-w-lead text-body text-muted-foreground">{children}</p>
      <Link href="/" className="text-control underline underline-offset-2">
        Start a new idea
      </Link>
    </section>
  );
}

/** `/ideas/[ideaId]`: the idea and its latest run, live (ui-context.md, Routes). */
export function IdeaConversation({ ideaId }: { ideaId: string }) {
  const idea = useIdea(ideaId);
  const run = useLatestRun(ideaId);
  const workspaceId = useWorkspaceId();

  if (idea.isPending || run.isPending) return <ConversationSkeleton />;
  const error = idea.error ?? run.error;
  if (error instanceof ApiError && error.status === 404) {
    return <ConversationProblem title="Idea not found">It may have been archived, or it belongs to another workspace.</ConversationProblem>;
  }
  if (error || !idea.data) {
    return <ConversationProblem title="Could not load this idea">{describeError(error)}</ConversationProblem>;
  }
  if (!run.data) return <NoRunConversation idea={idea.data} />;
  // A new run, or a new workspace, starts from a fresh state: the stream replays from the start.
  return <RunConversation key={`${workspaceId}:${run.data.id}`} idea={idea.data} run={run.data} />;
}
