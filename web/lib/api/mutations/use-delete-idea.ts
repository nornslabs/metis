"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queries/keys";

/** Archives an idea (`DELETE /v1/ideas/{idea_id}`). */
export function useDeleteIdea() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (ideaId: string) => {
      await apiClient.DELETE("/v1/ideas/{idea_id}", {
        params: { path: { idea_id: ideaId } },
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.allIdeas() }),
  });
}
