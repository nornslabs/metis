"use client";

import { useInfiniteQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import type { components } from "@/lib/api/schema";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

export const IDEAS_PAGE_SIZE = 20;

export type IdeaFilter = components["schemas"]["IdeaFilter"];

export interface IdeasQuery {
  /** Title search; blank means none. */
  q?: string;
  filter?: IdeaFilter;
}

/** The workspace's ideas, latest activity first, a page at a time (`GET /v1/ideas`, cursor). */
export function useIdeas({ q = "", filter = "all" }: IdeasQuery = {}) {
  const workspaceId = useWorkspaceId();
  return useInfiniteQuery({
    queryKey: queryKeys.ideas(workspaceId, q, filter),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      bodyOf(
        await apiClient.GET("/v1/ideas", {
          params: { query: { limit: IDEAS_PAGE_SIZE, cursor: pageParam, q: q || null, filter } },
        }),
      ),
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    placeholderData: (previous) => previous,
  });
}
