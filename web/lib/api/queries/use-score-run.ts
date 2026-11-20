"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

/** One stored score run with its parameters (`GET /v1/scores/{id}`); runs only for a given id. */
export function useScoreRun(ideaId: string, scoreRunId: string | null) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.scoreRun(workspaceId, ideaId, scoreRunId ?? ""),
    enabled: scoreRunId !== null,
    staleTime: Infinity,
    queryFn: async () =>
      bodyOf(await apiClient.GET("/v1/scores/{score_run_id}", { params: { path: { score_run_id: scoreRunId ?? "" } } })),
  });
}
