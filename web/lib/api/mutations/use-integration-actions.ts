"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queries/keys";
import { bodyOf } from "@/lib/api/result";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

/**
 * Starts the Linear OAuth flow (`POST /v1/integrations/linear/connect`): the answer is the page
 * Linear sends the browser to. `redirectTo` is where the server returns the browser afterwards.
 */
export function useConnectLinear() {
  return useMutation({
    mutationFn: async (redirectTo: string) =>
      bodyOf(
        await apiClient.POST("/v1/integrations/{provider}/connect", {
          params: { path: { provider: "linear" } },
          body: { redirect_to: redirectTo },
        }),
      ).authorize_url,
  });
}

/** Disconnects Linear (`DELETE /v1/integrations/linear`, owners only) and refreshes the status. */
export function useDisconnectLinear() {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();
  return useMutation({
    mutationFn: async () => {
      await apiClient.DELETE("/v1/integrations/{provider}", { params: { path: { provider: "linear" } } });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.integrations(workspaceId) }),
  });
}
