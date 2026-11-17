"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";

import type { ProviderKind } from "./use-save-key";

/**
 * Checks a saved key with one provider call (`POST /v1/settings/keys/{kind}/test`). A failure is a
 * 502 `provider.upstream_error` the caller shows inline; the server still records the result, so
 * settings are refetched either way.
 */
export function useTestKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (kind: ProviderKind) =>
      bodyOf(
        await apiClient.POST("/v1/settings/keys/{kind}/test", { params: { path: { kind } } }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
}
