"use client";

import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useMemo, useSyncExternalStore } from "react";

import { fetchPlan, patchPlanTask, resumeWithPhases } from "@/lib/api/mutations/plan";
import { queryKeys } from "@/lib/api/queries/keys";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";
import { PhaseReview, type PhaseReviewState } from "@/lib/plan/phase-review";
import { PlanEditor, type PlanEditorState } from "@/lib/plan/plan-editor";
import type { Plan } from "@/lib/schemas/plan";

/** Stores per query client, so none outlives the client (and the session) it was built for. */
const editorsByClient = new WeakMap<QueryClient, Map<string, PlanEditor>>();
const reviewsByClient = new WeakMap<QueryClient, Map<string, PhaseReview>>();

function cached<T>(registry: WeakMap<QueryClient, Map<string, T>>, client: QueryClient, id: string, create: () => T): T {
  const stores = registry.get(client) ?? new Map<string, T>();
  registry.set(client, stores);
  const existing = stores.get(id);
  if (existing) return existing;
  const created = create();
  stores.set(id, created);
  return created;
}

/** The one task editor of an idea's plan, shared by the pane body and its footer. */
export function usePlanEditor(ideaId: string): PlanEditor {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();
  return useMemo(
    () =>
      cached(editorsByClient, queryClient, `${workspaceId ?? ""}:${ideaId}`, () => {
        const key = queryKeys.plan(workspaceId, ideaId);
        return new PlanEditor({
          current: () => queryClient.getQueryData<Plan | null>(key) ?? null,
          save: patchPlanTask,
          refresh: () => fetchPlan(ideaId),
          publish: (plan) => queryClient.setQueryData(key, plan),
        });
      }),
    [queryClient, workspaceId, ideaId],
  );
}

export function usePlanEditorState(editor: PlanEditor): PlanEditorState {
  return useSyncExternalStore(editor.subscribe, editor.getState, editor.getState);
}

/** The one phase review of an idea, shared by the pane, its footer and the chat prompt. */
export function usePhaseReview(ideaId: string): PhaseReview {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();
  return useMemo(
    () =>
      cached(
        reviewsByClient,
        queryClient,
        `${workspaceId ?? ""}:${ideaId}`,
        () =>
          new PhaseReview({
            resume: async (runId, phases) => {
              await resumeWithPhases(runId, phases);
              // The run moves on to write tasks: refetch what depends on it.
              void queryClient.invalidateQueries({ queryKey: queryKeys.latestRun(workspaceId, ideaId) });
              void queryClient.invalidateQueries({ queryKey: queryKeys.idea(workspaceId, ideaId), exact: true });
            },
          }),
      ),
    [queryClient, workspaceId, ideaId],
  );
}

export function usePhaseReviewState(review: PhaseReview): PhaseReviewState {
  return useSyncExternalStore(review.subscribe, review.getState, review.getState);
}
