"use client";

import { useMemo } from "react";

import { useLatestScore } from "@/lib/api/queries/use-latest-score";
import { useScoreHistory } from "@/lib/api/queries/use-score-history";
import { useSuggestions } from "@/lib/api/queries/use-suggestions";
import { scoreVersions } from "@/lib/scores/versions";
import { groupByScoreRun } from "@/lib/scores/view";

/**
 * Everything the Score and Suggestions panes, their chat cards and the export read, in one place:
 * the latest score, the history as versions (newest first), and the newest score run's suggestions.
 */
export function useScoreOutputs(ideaId: string) {
  const latest = useLatestScore(ideaId);
  const score = latest.data ?? null;
  const history = useScoreHistory(ideaId, score !== null);
  const suggestions = useSuggestions(ideaId, score !== null);
  const versions = useMemo(() => scoreVersions(history.data ?? []), [history.data]);
  const newestSuggestions = useMemo(() => groupByScoreRun(suggestions.data ?? [])[0] ?? [], [suggestions.data]);
  return { latest, score, history, suggestions, versions, newestSuggestions };
}
