import { getWorkspaceId } from "@/lib/api/workspace";

/** Query keys. Workspace-scoped resources include the chosen workspace id. */
export const queryKeys = {
  me: () => ["me"] as const,
  workspaces: () => ["workspaces"] as const,
  currentWorkspace: () => ["workspaces", "current", getWorkspaceId()] as const,
};
