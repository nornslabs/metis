"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import type { components } from "@/lib/api/schema";

export type ProviderKind = components["schemas"]["ProviderKind"];
export type PutKeyInput = {
  kind: ProviderKind;
  body: components["schemas"]["PutProviderKeyRequest"];
};

/** Saves or replaces a provider key (`PUT /v1/settings/keys/{kind}`); the answer is masked. */
export function useSaveKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ kind, body }: PutKeyInput) =>
      bodyOf(await apiClient.PUT("/v1/settings/keys/{kind}", { params: { path: { kind } }, body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
}
