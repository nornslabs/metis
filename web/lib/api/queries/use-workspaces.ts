"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";

import { queryKeys } from "./keys";

/** Every workspace the caller belongs to (`GET /v1/workspaces`). */
export function useWorkspaces() {
  return useQuery({
    queryKey: queryKeys.workspaces(),
    queryFn: async () => bodyOf(await apiClient.GET("/v1/workspaces")),
  });
}
