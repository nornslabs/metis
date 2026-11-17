"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import type { components } from "@/lib/api/schema";

/** Changes run limits (`PATCH /v1/settings`); `version` must be the one read, or the API answers 409. */
export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: components["schemas"]["SettingsPatch"]) =>
      bodyOf(await apiClient.PATCH("/v1/settings", { body })),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
}
