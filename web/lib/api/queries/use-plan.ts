"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchPlan } from "@/lib/api/mutations/plan";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

/**
 * The idea's newest plan, `null` while there is none. Runs only when `enabled` (once the run can
 * have a plan), so no request is sent before one can exist.
 */
export function usePlan(ideaId: string, enabled: boolean) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.plan(workspaceId, ideaId),
    enabled,
    queryFn: () => fetchPlan(ideaId),
  });
}
