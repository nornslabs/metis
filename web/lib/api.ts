"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
// import type { paths } from "@/lib/api/schema"; // Will be available after gen:api runs

// API base URL from env
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown
  ) {
    const detail = (body as Record<string, unknown> | undefined)?.detail as string | undefined;
    const title = (body as Record<string, unknown> | undefined)?.title as string | undefined;
    super(detail || title || `API Error: ${status}`);
    this.name = "ApiError";
  }
}

// TanStack Query hooks for all API endpoints
// These are the main exports for components to use

// Types from the generated schema (will be available after gen:api runs)
// For now, we define minimal types that match the server schemas

export interface UserDto {
  id: string;
  email: string;
  name: string | null;
  image: string | null;
  created_at: string;
}

export interface WorkspaceDto {
  id: string;
  name: string;
  is_personal: boolean;
  created_by: string;
  created_at: string;
}

export interface MembershipDto {
  workspace: WorkspaceDto;
  role: "owner" | "admin" | "member";
}

export interface MeResponse {
  user: UserDto;
  workspaces: MembershipDto[];
  current_workspace: MembershipDto;
}

export interface WorkspaceListResponse {
  items: MembershipDto[];
  next_cursor: string | null;
}

export interface CreateWorkspaceRequest {
  name: string;
}

export interface CreateWorkspaceResponse {
  workspace: WorkspaceDto;
  role: "owner";
}

export interface ProviderKeyDto {
  kind: "llm" | "exa";
  masked_key: string;
  created_at: string;
  updated_at: string;
}

export interface SettingsResponse {
  provider_keys: Record<string, ProviderKeyDto>;
  workspace_settings: {
    run_budget_usd: number;
    max_steps: number;
    version: number;
  };
}

export interface UpdateSettingsRequest {
  run_budget_usd?: number;
  max_steps?: number;
  version: number;
}

export interface UpdateSettingsResponse {
  run_budget_usd: number;
  max_steps: number;
  version: number;
}

export interface KeyTestResponse {
  ok: boolean;
  error?: string;
}

// Query keys
export const queryKeys = {
  me: ["me"] as const,
  workspaces: ["workspaces"] as const,
  settings: ["settings"] as const,
};

// Authenticated fetch wrapper for TanStack Query
async function apiFetch<T>(
  path: string,
  init: RequestInit & { apiToken: string; workspaceId?: string } = { apiToken: "" }
): Promise<T> {
  const { apiToken, workspaceId, headers, ...rest } = init;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiToken}`,
      "X-Workspace-Id": workspaceId || "",
      ...headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new ApiError(response.status, error);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// Extended session type with apiToken
interface ExtendedSession {
  user: {
    id: string;
    email: string;
    name: string | null;
    image: string | null;
  };
  apiToken?: string;
  expires: string;
}

// Hook to get the API token from session
export function useApiToken(): string | undefined {
  const { data: session } = useSession();
  return (session as ExtendedSession | null | undefined)?.apiToken;
}

// Hook to get the current workspace ID (from localStorage or context)
export function useWorkspaceId(): string | undefined {
  if (typeof window === "undefined") return undefined;
  return localStorage.getItem("metis_workspace_id") || undefined;
}

// API hooks
export function useMe() {
  const apiToken = useApiToken();

  return useQuery({
    queryKey: queryKeys.me,
    queryFn: () => apiFetch<MeResponse>("/me", { apiToken: apiToken! }),
    enabled: !!apiToken,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useWorkspaces() {
  const apiToken = useApiToken();

  return useQuery({
    queryKey: queryKeys.workspaces,
    queryFn: () => apiFetch<WorkspaceListResponse>("/workspaces", { apiToken: apiToken! }),
    enabled: !!apiToken,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateWorkspace() {
  const queryClient = useQueryClient();
  const apiToken = useApiToken();

  return useMutation({
    mutationFn: (name: string) =>
      apiFetch<CreateWorkspaceResponse>("/workspaces", {
        apiToken: apiToken!,
        method: "POST",
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.workspaces });
      queryClient.invalidateQueries({ queryKey: queryKeys.me });
    },
  });
}

export function useSettings() {
  const apiToken = useApiToken();
  const workspaceId = useWorkspaceId();

  return useQuery({
    queryKey: [...queryKeys.settings, workspaceId],
    queryFn: () =>
      apiFetch<SettingsResponse>("/settings", {
        apiToken: apiToken!,
        workspaceId,
      }),
    enabled: !!apiToken,
    staleTime: 30 * 1000, // 30 seconds
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  const apiToken = useApiToken();
  const workspaceId = useWorkspaceId();

  return useMutation({
    mutationFn: (data: UpdateSettingsRequest) =>
      apiFetch<UpdateSettingsResponse>("/settings", {
        apiToken: apiToken!,
        workspaceId,
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.settings });
    },
  });
}

export function useSetProviderKey() {
  const queryClient = useQueryClient();
  const apiToken = useApiToken();
  const workspaceId = useWorkspaceId();

  return useMutation({
    mutationFn: ({ kind, key }: { kind: "llm" | "exa"; key: string }) =>
      apiFetch<ProviderKeyDto>(`/settings/keys/${kind}`, {
        apiToken: apiToken!,
        workspaceId,
        method: "PUT",
        body: JSON.stringify({ key }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.settings });
    },
  });
}

export function useDeleteProviderKey() {
  const queryClient = useQueryClient();
  const apiToken = useApiToken();
  const workspaceId = useWorkspaceId();

  return useMutation({
    mutationFn: (kind: "llm" | "exa") =>
      apiFetch<void>(`/settings/keys/${kind}`, {
        apiToken: apiToken!,
        workspaceId,
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.settings });
    },
  });
}

export function useTestProviderKey() {
  const apiToken = useApiToken();
  const workspaceId = useWorkspaceId();

  return useMutation({
    mutationFn: (kind: "llm" | "exa") =>
      apiFetch<KeyTestResponse>(`/settings/keys/${kind}/test`, {
        apiToken: apiToken!,
        workspaceId,
        method: "POST",
      }),
  });
}