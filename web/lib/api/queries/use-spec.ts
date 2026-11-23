"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchSpecOverview } from "@/lib/api/mutations/spec";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

/**
 * The idea's latest and confirmed spec versions. Runs only when `enabled` (once the run can have a
 * spec), so no request is sent before one can exist.
 */
export function useSpec(ideaId: string, enabled: boolean) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.spec(workspaceId, ideaId),
    enabled,
    queryFn: () => fetchSpecOverview(ideaId),
  });
}
