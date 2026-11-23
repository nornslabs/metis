import type { components } from "@/lib/api/schema";

type Idea = components["schemas"]["Idea"];
type IdeaScoreSummary = components["schemas"]["IdeaScoreSummary"];
type ScoreBand = components["schemas"]["ScoreBand"];
type Stage = components["schemas"]["Stage"];

/** What one history row shows: the idea joined with its score trend. */
export interface HistoryRow {
  id: string;
  title: string;
  stage: Stage;
  /** Last activity (`updated_at`, ISO). */
  activeAt: string;
  /** The latest score, or null when the idea has none. */
  score: number | null;
  band: ScoreBand | null;
  /** Score totals per version, oldest first (empty when unscored). */
  totals: readonly number[];
}

/** Joins an idea with its summary (if any). The summary's last total is the latest score. */
export function toHistoryRow(idea: Idea, summary: IdeaScoreSummary | undefined): HistoryRow {
  const totals = summary?.totals ?? [];
  return {
    id: idea.id,
    title: idea.title,
    stage: idea.stage,
    activeAt: idea.updated_at,
    score: totals.at(-1) ?? idea.current_score,
    band: summary?.band ?? null,
    totals,
  };
}
