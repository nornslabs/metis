"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

/** The idea's suggestions, newest score run first (`GET /v1/ideas/{id}/suggestions`). */
export function useSuggestions(ideaId: string, enabled: boolean) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.suggestions(workspaceId, ideaId),
    enabled,
    queryFn: async () =>
      bodyOf(await apiClient.GET("/v1/ideas/{idea_id}/suggestions", { params: { path: { idea_id: ideaId } } })).items,
  });
}
