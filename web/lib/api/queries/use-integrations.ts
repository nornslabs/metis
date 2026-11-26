"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { bodyOf } from "@/lib/api/result";
import type { components } from "@/lib/api/schema";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { queryKeys } from "./keys";

export type IntegrationView = components["schemas"]["IntegrationView"];
export type LinearTool = components["schemas"]["ToolInfo"];
export type IntegrationStatus = IntegrationView["status"];

/** Code of the 409 `GET .../tools` answers when the connection is missing or expired. */
const NOT_USABLE_STATUS = 409;
const TOOLS_STALE_MS = 60_000;

/** Every provider's connection for the workspace (`GET /v1/integrations`). */
export function useIntegrations() {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.integrations(workspaceId),
    queryFn: async () => bodyOf(await apiClient.GET("/v1/integrations")).items,
  });
}

/** The Linear connection, or `not_connected` while the list loads or has no Linear row. */
export function useLinearStatus(): { status: IntegrationStatus; connection: IntegrationView | null; isPending: boolean } {
  const list = useIntegrations();
  const connection = list.data?.find((item) => item.provider === "linear") ?? null;
  return { status: connection?.status ?? "not_connected", connection, isPending: list.isPending };
}

/**
 * The tools Linear offers, read when `enabled`. A `409` (not connected or expired) is a normal
 * answer, not a failure: `unavailable` is true then.
 */
export function useLinearTools(enabled: boolean) {
  const workspaceId = useWorkspaceId();
  const query = useQuery({
    queryKey: queryKeys.linearTools(workspaceId),
    enabled,
    staleTime: TOOLS_STALE_MS,
    retry: false,
    queryFn: async () => bodyOf(await apiClient.GET("/v1/integrations/{provider}/tools", { params: { path: { provider: "linear" } } })).items,
  });
  const unavailable = query.error instanceof ApiError && query.error.status === NOT_USABLE_STATUS;
  return { ...query, unavailable };
}
