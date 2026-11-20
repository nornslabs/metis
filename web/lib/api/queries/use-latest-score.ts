"use client";

import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";
import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

const NOT_FOUND = "score.not_found";

/** The idea's newest score run (`GET /v1/ideas/{id}/scores/latest`), or `null` before the first one. */
export function useLatestScore(ideaId: string) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.latestScore(workspaceId, ideaId),
    queryFn: async () => {
      try {
        return bodyOf(await apiClient.GET("/v1/ideas/{idea_id}/scores/latest", { params: { path: { idea_id: ideaId } } }));
      } catch (caught) {
        if (caught instanceof ApiError && caught.code === NOT_FOUND) return null;
        throw caught;
      }
    },
  });
}
