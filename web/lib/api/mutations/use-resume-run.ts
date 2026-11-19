"use client";

import { useMutation } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";

export type ResumeRunInput = {
  runId: string;
  /** Text for a question, `true` / `false` for an approval. */
  value: string | boolean;
};

/**
 * Answers the question (or approval) a run waits on (`POST /v1/runs/{id}/resume`). Only works from
 * `awaiting_user`; otherwise `409 run.invalid_state`.
 */
export function useResumeRun() {
  return useMutation({
    mutationFn: async ({ runId, value }: ResumeRunInput) =>
      bodyOf(
        await apiClient.POST("/v1/runs/{run_id}/resume", {
          params: { path: { run_id: runId } },
          body: { value },
        }),
      ),
  });
}
