"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

import type { ProviderKind } from "./use-save-key";

/** Removes a provider key (`DELETE /v1/settings/keys/{kind}`). */
export function useDeleteKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (kind: ProviderKind) => {
      await apiClient.DELETE("/v1/settings/keys/{kind}", { params: { path: { kind } } });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
}
