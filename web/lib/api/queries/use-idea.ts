"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

/** One idea of the current workspace (`GET /v1/ideas/{id}`); 404 `idea.not_found` when hidden. */
export function useIdea(ideaId: string) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.idea(workspaceId, ideaId),
    queryFn: async () =>
      bodyOf(await apiClient.GET("/v1/ideas/{idea_id}", { params: { path: { idea_id: ideaId } } })),
    placeholderData: undefined,
    staleTime: 0,
    gcTime: 0,
  });
}
