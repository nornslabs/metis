"use client";

import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";
import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

const NOT_FOUND = "research.not_found";

/**
 * The idea's latest closed research (`GET /v1/ideas/{id}/research`), or `null` before the
 * Researcher has finished: `404 research.not_found` is an empty state, not an error. It runs only
 * when `enabled` (once the Researcher has started), so no request is sent before research can exist.
 */
export function useResearch(ideaId: string, enabled: boolean) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.research(workspaceId, ideaId),
    enabled,
    queryFn: async () => {
      try {
        return bodyOf(await apiClient.GET("/v1/ideas/{idea_id}/research", { params: { path: { idea_id: ideaId } } }));
      } catch (caught) {
        if (caught instanceof ApiError && caught.code === NOT_FOUND) return null;
        throw caught;
      }
    },
  });
}
