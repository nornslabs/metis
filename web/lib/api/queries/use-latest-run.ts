"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

/** The idea's newest run (`GET /v1/ideas/{id}/runs?limit=1`), or `null` when it has none. */
export function useLatestRun(ideaId: string) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.latestRun(workspaceId, ideaId),
    queryFn: async () => {
      const page = bodyOf(
        await apiClient.GET("/v1/ideas/{idea_id}/runs", {
          params: { path: { idea_id: ideaId }, query: { limit: 1 } },
        }),
      );
      return page.items[0] ?? null;
    },
    placeholderData: undefined,
    staleTime: 0,
    gcTime: 0,
  });
}
