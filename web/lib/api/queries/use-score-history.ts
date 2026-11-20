"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

/** The idea's score runs without parameters, newest first (`GET /v1/ideas/{id}/scores`). */
export function useScoreHistory(ideaId: string, enabled: boolean) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.scoreHistory(workspaceId, ideaId),
    enabled,
    queryFn: async () =>
      bodyOf(await apiClient.GET("/v1/ideas/{idea_id}/scores", { params: { path: { idea_id: ideaId } } })).items,
  });
}
