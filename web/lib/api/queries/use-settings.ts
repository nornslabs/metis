"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

/** Masked provider keys and run limits of the current workspace (`GET /v1/settings`). */
export function useSettings() {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.settings(workspaceId),
    queryFn: async () => bodyOf(await apiClient.GET("/v1/settings")),
  });
}
