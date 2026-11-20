"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queries/keys";
import { bodyOf } from "@/lib/api/result";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";
import type { Suggestion } from "@/lib/scores/view";

export type SetSuggestionStatusInput = { suggestionId: string; status: Suggestion["status"] };

/** Accepts, dismisses or reopens a suggestion (`PATCH /v1/suggestions/{id}`); the list refetches. */
export function useSetSuggestionStatus(ideaId: string) {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();
  return useMutation({
    mutationFn: async ({ suggestionId, status }: SetSuggestionStatusInput) =>
      bodyOf(
        await apiClient.PATCH("/v1/suggestions/{suggestion_id}", {
          params: { path: { suggestion_id: suggestionId } },
          body: { status },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.suggestions(workspaceId, ideaId) }),
  });
}
