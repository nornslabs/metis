"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queries/keys";
import { bodyOf } from "@/lib/api/result";

export type RefreshKind = "recheck-market" | "rescore";

export type RefreshScoreInput = {
  ideaId: string;
  kind: RefreshKind;
  /** One key per attempt: a resend with the same key returns the same run. */
  idempotencyKey: string;
};

/**
 * Starts a refresh run: `recheck-market` researches again and scores, `rescore` scores on the
 * research the idea already has. Both return the new run's id; 409 `run.already_running` if one is active.
 */
export function useRefreshScore() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ ideaId, kind, idempotencyKey }: RefreshScoreInput) => {
      const options = { params: { path: { idea_id: ideaId }, header: { "Idempotency-Key": idempotencyKey } } };
      return bodyOf(
        kind === "recheck-market"
          ? await apiClient.POST("/v1/ideas/{idea_id}/recheck-market", options)
          : await apiClient.POST("/v1/ideas/{idea_id}/rescore", options),
      );
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.allIdeas() }),
  });
}
