/** Query keys. Workspace-scoped resources include the chosen workspace id. */
export const queryKeys = {
  me: () => ["me"] as const,
  workspaces: () => ["workspaces"] as const,
  currentWorkspace: (workspaceId: string | null) =>
    ["workspaces", "current", workspaceId] as const,
  settings: (workspaceId: string | null) => ["settings", workspaceId] as const,
  /** Prefix of every idea query (list, ideas, runs), for invalidation after a write. */
  allIdeas: () => ["ideas"] as const,
  ideas: (workspaceId: string | null) => ["ideas", workspaceId, "list"] as const,
  idea: (workspaceId: string | null, ideaId: string) => ["ideas", workspaceId, ideaId] as const,
  latestRun: (workspaceId: string | null, ideaId: string) =>
    ["ideas", workspaceId, ideaId, "latest-run"] as const,
  /** The idea's interview turns (under the idea key, so a refresh of the idea refetches them). */
  interview: (workspaceId: string | null, ideaId: string) =>
    ["ideas", workspaceId, ideaId, "interview"] as const,
  /** The idea's latest research snapshot (also under the idea key). */
  research: (workspaceId: string | null, ideaId: string) =>
    ["ideas", workspaceId, ideaId, "research"] as const,
};
