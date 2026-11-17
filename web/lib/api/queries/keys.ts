/** Query keys. Workspace-scoped resources include the chosen workspace id. */
export const queryKeys = {
  me: () => ["me"] as const,
  workspaces: () => ["workspaces"] as const,
  currentWorkspace: (workspaceId: string | null) =>
    ["workspaces", "current", workspaceId] as const,
  settings: (workspaceId: string | null) => ["settings", workspaceId] as const,
};
