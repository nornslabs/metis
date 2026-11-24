"use client";

import { SuggestionCard } from "@/components/suggestions/suggestion-card";
import { describeError } from "@/lib/api/errors";
import { useSetSuggestionStatus } from "@/lib/api/mutations/use-set-suggestion-status";
import { appliedIn, type ScoreVersion } from "@/lib/scores/versions";
import { groupByScoreRun, type Suggestion } from "@/lib/scores/view";

interface SuggestionListProps {
  ideaId: string;
  suggestions: readonly Suggestion[];
  /** The score versions, to tell which accepted suggestions a later version applied. */
  versions: readonly ScoreVersion[];
}

function Cards({
  group,
  versions,
  pendingId,
  onStatus,
}: {
  group: readonly Suggestion[];
  versions: readonly ScoreVersion[];
  pendingId: string | null;
  onStatus: (id: string, status: Suggestion["status"]) => void;
}) {
  return (
    <ul className="flex flex-col gap-1.5">
      {group.map((suggestion) => (
        <SuggestionCard
          key={suggestion.id}
          suggestion={suggestion}
          appliedIn={appliedIn(suggestion, versions)}
          disabled={pendingId === suggestion.id}
          onStatus={(status) => onStatus(suggestion.id, status)}
        />
      ))}
    </ul>
  );
}

/** The newest score run's suggestions; older runs' suggestions sit in a collapsed block. */
export function SuggestionList({ ideaId, suggestions, versions }: SuggestionListProps) {
  const setStatus = useSetSuggestionStatus(ideaId);
  const [latest, ...earlier] = groupByScoreRun(suggestions);
  if (!latest) return null;
  const pendingId = setStatus.isPending ? setStatus.variables.suggestionId : null;
  const onStatus = (suggestionId: string, status: Suggestion["status"]) => setStatus.mutate({ suggestionId, status });
  return (
    <section aria-label="Suggestions" className="flex flex-col gap-1.5">
      <Cards group={latest} versions={versions} pendingId={pendingId} onStatus={onStatus} />
      {setStatus.isError ? (
        <p role="alert" className="text-meta text-destructive">
          Could not save your choice. {describeError(setStatus.error)}
        </p>
      ) : null}
      {earlier.length > 0 ? (
        <details className="flex flex-col gap-1.5">
          <summary className="cursor-pointer text-control text-muted-foreground">Earlier suggestions</summary>
          <div className="mt-1.5 flex flex-col gap-1.5">
            {earlier.map((group) => (
              <Cards key={group[0]?.score_run_id} group={group} versions={versions} pendingId={pendingId} onStatus={onStatus} />
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
}
