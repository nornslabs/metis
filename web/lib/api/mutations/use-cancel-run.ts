"use client";

import { useMutation } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";

/**
 * Asks to stop a run (`POST /v1/runs/{id}/cancel`). `status` is `cancelled` when done at once and
 * `running` while the worker stops it; the stream's `run_status` confirms either way.
 */
export function useCancelRun() {
  return useMutation({
    mutationFn: async (runId: string) =>
      bodyOf(await apiClient.POST("/v1/runs/{run_id}/cancel", { params: { path: { run_id: runId } } })),
  });
}
