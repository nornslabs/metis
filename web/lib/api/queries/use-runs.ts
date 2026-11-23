"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";
import { oldestFirst } from "./runs-order";

/** The most runs the chat loads for one idea (the API's page maximum). */
const RUN_HISTORY_LIMIT = 100;

/**
 * The idea's runs, oldest first (`GET /v1/ideas/{id}/runs` returns them newest first). The chat
 * shows each run as a turn in this order, so the transcript stays chronological.
 */
export function useRuns(ideaId: string) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.runs(workspaceId, ideaId),
    queryFn: async () => {
      const page = bodyOf(
        await apiClient.GET("/v1/ideas/{idea_id}/runs", {
          params: { path: { idea_id: ideaId }, query: { limit: RUN_HISTORY_LIMIT } },
        }),
      );
      return oldestFirst(page.items);
    },
    placeholderData: undefined,
    staleTime: 0,
    gcTime: 0,
  });
}
