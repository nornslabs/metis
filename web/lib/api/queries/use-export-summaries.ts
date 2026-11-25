"use client";

import { useQueries, useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";
import { exportSummarySchema, type ExportSummary } from "@/lib/schemas/export";

import { SUMMARY_IDS_MAX, chunk } from "./chunk";
import { queryKeys } from "./keys";

const SUMMARIES_STALE_MS = 30_000;

async function fetchSummaries(ids: readonly string[]): Promise<ExportSummary[]> {
  const result = await apiClient.GET("/v1/exports/summaries", { params: { query: { idea_ids: ids.join(",") } } });
  return bodyOf(result).items.map((item) => exportSummarySchema.parse(item));
}

/** The newest finished export of each given idea, by idea id; ideas never exported are absent. */
export function useExportSummaries(ideaIds: readonly string[]): ReadonlyMap<string, ExportSummary> {
  const workspaceId = useWorkspaceId();
  const results = useQueries({
    queries: chunk(ideaIds, SUMMARY_IDS_MAX).map((ids) => ({
      queryKey: queryKeys.exportSummaries(workspaceId, ids),
      queryFn: () => fetchSummaries(ids),
      staleTime: SUMMARIES_STALE_MS,
    })),
  });
  const summaries = new Map<string, ExportSummary>();
  for (const result of results) {
    for (const item of result.data ?? []) summaries.set(item.idea_id, item);
  }
  return summaries;
}

/** The newest finished export of one idea, or null. `enabled` turns the read off. */
export function useIdeaExport(ideaId: string, enabled = true): { summary: ExportSummary | null; isPending: boolean } {
  const workspaceId = useWorkspaceId();
  const query = useQuery({
    queryKey: queryKeys.exportSummaries(workspaceId, [ideaId]),
    queryFn: () => fetchSummaries([ideaId]),
    staleTime: SUMMARIES_STALE_MS,
    enabled,
  });
  return { summary: query.data?.[0] ?? null, isPending: enabled && query.isPending };
}
