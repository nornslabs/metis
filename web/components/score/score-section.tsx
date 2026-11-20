"use client";

import { RefreshActions } from "@/components/score/refresh-actions";
import { ScoreCard } from "@/components/score/score-card";
import { ScoreCompare } from "@/components/score/score-compare";
import { SectionHeading } from "@/components/score/section-heading";
import { ScoreHistoryChart } from "@/components/score/score-history-chart";
import { SuggestionList } from "@/components/suggestions/suggestion-list";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { describeError } from "@/lib/api/errors";
import { useLatestScore } from "@/lib/api/queries/use-latest-score";
import { useScoreHistory } from "@/lib/api/queries/use-score-history";
import { useSuggestions } from "@/lib/api/queries/use-suggestions";

interface ScoreSectionProps {
  ideaId: string;
  /** True while a run of this idea can still change (the refresh buttons wait for it). */
  runActive: boolean;
  /** True once a Scorer step has started: only then is a loading state worth showing. */
  scoringStarted: boolean;
}

/** The idea's score: card, history, compare and suggestions. Nothing before the first score exists. */
export function ScoreSection({ ideaId, runActive, scoringStarted }: ScoreSectionProps) {
  const latest = useLatestScore(ideaId);
  const hasScore = Boolean(latest.data);
  const history = useScoreHistory(ideaId, hasScore);
  const suggestions = useSuggestions(ideaId, hasScore);

  if (latest.isError && !scoringStarted) return null;
  if (latest.isError) {
    return (
      <div role="alert" className="flex flex-wrap items-center gap-2 border border-destructive/40 px-2.5 py-1.5">
        <span className="text-control">Could not load the score. {describeError(latest.error)}</span>
        <Button type="button" variant="outline" size="sm" className="ml-auto" onClick={() => void latest.refetch()}>
          Retry
        </Button>
      </div>
    );
  }
  if (latest.isPending) return scoringStarted ? <Skeleton aria-label="Loading score" className="h-32 w-full" /> : null;
  if (!latest.data) return null;

  const items = suggestions.data ?? [];
  return (
    <div className="flex flex-col gap-3">
      <ScoreCard score={latest.data} actions={<RefreshActions ideaId={ideaId} runActive={runActive} />} />
      {history.data ? (
        <section aria-label="History" className="flex flex-col gap-2">
          <SectionHeading>History</SectionHeading>
          <ScoreHistoryChart history={history.data} />
          <ScoreCompare ideaId={ideaId} history={history.data} />
        </section>
      ) : null}
      <SuggestionList ideaId={ideaId} suggestions={items} />
    </div>
  );
}
