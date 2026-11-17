"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";

import { queryKeys } from "./keys";

/** The signed-in user (`GET /v1/auth/me`). */
export function useMe() {
  return useQuery({
    queryKey: queryKeys.me(),
    queryFn: async () => bodyOf(await apiClient.GET("/v1/auth/me")),
  });
}
