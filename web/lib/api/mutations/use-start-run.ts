"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queries/keys";
import { bodyOf } from "@/lib/api/result";

export type StartRunInput = {
  ideaId: string;
  /** One key per start attempt: a resend with the same key returns the same run. */
  idempotencyKey: string;
};

/** Starts a run of an idea (`POST /v1/ideas/{id}/runs`); 409 `run.already_running` if one is active. */
export function useStartRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ ideaId, idempotencyKey }: StartRunInput) =>
      bodyOf(
        await apiClient.POST("/v1/ideas/{idea_id}/runs", {
          params: { path: { idea_id: ideaId }, header: { "Idempotency-Key": idempotencyKey } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.allIdeas() }),
  });
}

/** A fresh idempotency key for a new start attempt. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
