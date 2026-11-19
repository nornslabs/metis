"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

/** The idea's interview turns across all runs, oldest first (`GET /v1/ideas/{id}/interview`). */
export function useInterview(ideaId: string) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.interview(workspaceId, ideaId),
    queryFn: async () =>
      bodyOf(
        await apiClient.GET("/v1/ideas/{idea_id}/interview", { params: { path: { idea_id: ideaId } } }),
      ).items,
  });
}
