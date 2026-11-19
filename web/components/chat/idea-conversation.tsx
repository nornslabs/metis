"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { NoRunConversation, RunConversation } from "@/components/chat/run-conversation";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, describeError } from "@/lib/api/errors";
import { useIdea } from "@/lib/api/queries/use-idea";
import { useLatestRun } from "@/lib/api/queries/use-latest-run";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

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
