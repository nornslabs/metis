"use client";

import { useQueries } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import type { components } from "@/lib/api/schema";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { SUMMARY_IDS_MAX, chunk } from "./chunk";
import { queryKeys } from "./keys";

type IdeaScoreSummary = components["schemas"]["IdeaScoreSummary"];

/** A page of trends is reused for this long before it is fetched again. */
const SUMMARIES_STALE_MS = 30_000;

/**
 * Score trends (totals per version and band) of the given ideas, by idea id. One call per page of
 * ids already loaded, so a page is fetched once however the list grows. Unscored ideas are absent.
 */
export function useScoreSummaries(ideaIds: readonly string[]): ReadonlyMap<string, IdeaScoreSummary> {
  const workspaceId = useWorkspaceId();
  const results = useQueries({
    queries: chunk(ideaIds, SUMMARY_IDS_MAX).map((ids) => ({
      queryKey: queryKeys.scoreSummaries(workspaceId, ids),
      queryFn: async () =>
        bodyOf(
          await apiClient.GET("/v1/scores/summaries", { params: { query: { idea_ids: ids.join(",") } } }),
        ).items,
      staleTime: SUMMARIES_STALE_MS,
    })),
  });
  const summaries = new Map<string, IdeaScoreSummary>();
  for (const result of results) {
    for (const item of result.data ?? []) summaries.set(item.idea_id, item);
  }
  return summaries;
}
