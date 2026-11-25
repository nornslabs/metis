/** Query keys. Workspace-scoped resources include the chosen workspace id. */
export const queryKeys = {
  me: () => ["me"] as const,
  workspaces: () => ["workspaces"] as const,
  currentWorkspace: (workspaceId: string | null) =>
    ["workspaces", "current", workspaceId] as const,
  settings: (workspaceId: string | null) => ["settings", workspaceId] as const,
  /** Prefix of every idea query (list, ideas, runs), for invalidation after a write. */
  allIdeas: () => ["ideas"] as const,
  ideas: (workspaceId: string | null, q = "", filter = "all") =>
    ["ideas", workspaceId, "list", q, filter] as const,
  /** Score trends of the ideas in one list page (`GET /v1/scores/summaries`). */
  scoreSummaries: (workspaceId: string | null, ideaIds: readonly string[]) =>
    ["ideas", workspaceId, "score-summaries", ...ideaIds] as const,
  idea: (workspaceId: string | null, ideaId: string) => ["ideas", workspaceId, ideaId] as const,
  /** The idea's runs, oldest first (the chat shows each as a turn). */
  runs: (workspaceId: string | null, ideaId: string) =>
    ["ideas", workspaceId, ideaId, "runs"] as const,
  /** The idea's interview turns (under the idea key, so a refresh of the idea refetches them). */
  interview: (workspaceId: string | null, ideaId: string) =>
    ["ideas", workspaceId, ideaId, "interview"] as const,
  /** The idea's latest research snapshot (also under the idea key). */
  research: (workspaceId: string | null, ideaId: string) =>
    ["ideas", workspaceId, ideaId, "research"] as const,
  /** The idea's newest score run (under the idea key, so a refresh of the idea refetches it). */
  latestScore: (workspaceId: string | null, ideaId: string) =>
    ["ideas", workspaceId, ideaId, "scores", "latest"] as const,
  scoreHistory: (workspaceId: string | null, ideaId: string) =>
    ["ideas", workspaceId, ideaId, "scores", "history"] as const,
  /** One stored score run, for comparing two. Immutable, so never stale. */
  scoreRun: (workspaceId: string | null, ideaId: string, scoreRunId: string) =>
    ["ideas", workspaceId, ideaId, "scores", "run", scoreRunId] as const,
  /** The idea's latest and confirmed spec versions (also under the idea key). */
  spec: (workspaceId: string | null, ideaId: string) => ["ideas", workspaceId, ideaId, "spec"] as const,
  /** The version list; `latestNumber` is in the key so a newer version refetches it. */
  specVersions: (workspaceId: string | null, ideaId: string, latestNumber: number | null) =>
    ["ideas", workspaceId, ideaId, "spec-versions", latestNumber] as const,
  /** One version with its text. Immutable, never stale. */
  specVersion: (workspaceId: string | null, ideaId: string, number: number) =>
    ["ideas", workspaceId, ideaId, "spec-version", number] as const,
  /** The idea's newest plan, or null while there is none (also under the idea key). */
  plan: (workspaceId: string | null, ideaId: string) => ["ideas", workspaceId, ideaId, "plan"] as const,
  /** The workspace's MCP connections (`GET /v1/integrations`). */
  integrations: (workspaceId: string | null) => ["integrations", workspaceId] as const,
  /** The tools the connected Linear server offers. */
  linearTools: (workspaceId: string | null) => ["integrations", workspaceId, "linear", "tools"] as const,
  /** Newest finished exports of the ideas in one page (`GET /v1/exports/summaries`). */
  exportSummaries: (workspaceId: string | null, ideaIds: readonly string[]) =>
    ["exports", workspaceId, "summaries", ...ideaIds] as const,
  /** Prefix of every export summary query, for invalidation when an export ends. */
  allExportSummaries: () => ["exports"] as const,
  suggestions: (workspaceId: string | null, ideaId: string) =>
    ["ideas", workspaceId, ideaId, "suggestions"] as const,
};
