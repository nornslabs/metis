"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";

import { queryKeys } from "./keys";

/** The current workspace and the caller's role (`GET /v1/workspaces/current`). */
export function useCurrentWorkspace() {
  return useQuery({
    queryKey: queryKeys.currentWorkspace(),
    queryFn: async () => bodyOf(await apiClient.GET("/v1/workspaces/current")),
  });
}
