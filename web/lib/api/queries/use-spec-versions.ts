"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { fetchSpecVersion, fetchSpecVersions } from "@/lib/api/mutations/spec";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

/** Every version of the idea's spec without its text, newest first. Refetches when a newer version exists. */
export function useSpecVersions(ideaId: string, latestNumber: number | null) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.specVersions(workspaceId, ideaId, latestNumber),
    enabled: latestNumber !== null,
    queryFn: () => fetchSpecVersions(ideaId),
    placeholderData: keepPreviousData,
  });
}

/** One version with its text. A version never changes, so it is never refetched. */
export function useSpecVersion(ideaId: string, number: number | null) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.specVersion(workspaceId, ideaId, number ?? 0),
    enabled: number !== null,
    staleTime: Infinity,
    queryFn: () => fetchSpecVersion(ideaId, number ?? 0),
  });
}
