"use client";

import { useInfiniteQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

export const IDEAS_PAGE_SIZE = 10;

/** The workspace's ideas, newest first, a page at a time (`GET /v1/ideas`, cursor). */
export function useIdeas() {
  const workspaceId = useWorkspaceId();
  return useInfiniteQuery({
    queryKey: queryKeys.ideas(workspaceId),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      bodyOf(
        await apiClient.GET("/v1/ideas", {
          params: { query: { limit: IDEAS_PAGE_SIZE, cursor: pageParam } },
        }),
      ),
    getNextPageParam: (lastPage) => lastPage.next_cursor,
  });
}
