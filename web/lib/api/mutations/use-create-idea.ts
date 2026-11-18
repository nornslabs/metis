"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queries/keys";
import { bodyOf } from "@/lib/api/result";
import type { components } from "@/lib/api/schema";

/** Creates an idea in the current workspace (`POST /v1/ideas`). */
export function useCreateIdea() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: components["schemas"]["NewIdea"]) =>
      bodyOf(await apiClient.POST("/v1/ideas", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.allIdeas() }),
  });
}
