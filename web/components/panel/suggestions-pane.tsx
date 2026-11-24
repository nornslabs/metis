"use client";

import { PaneFooter } from "@/components/panel/pane-footer";
import { SuggestionList } from "@/components/suggestions/suggestion-list";
import { Skeleton } from "@/components/ui/skeleton";
import { describeError } from "@/lib/api/errors";
import { useScoreOutputs } from "@/lib/scores/use-score-outputs";

/** The Suggestions pane's body: angle cards for the newest score, with Accept / Dismiss / Undo. */
export function SuggestionsPaneBody({ ideaId }: { ideaId: string }) {
  const { suggestions, versions } = useScoreOutputs(ideaId);

  if (suggestions.isError) {
    return (
      <p role="alert" className="m-4 text-control text-destructive">
        Could not load the suggestions. {describeError(suggestions.error)}
      </p>
    );
  }
  if (!suggestions.data) return <Skeleton aria-label="Loading suggestions" className="m-4 h-24" />;
  return (
    <div className="p-4">
      <SuggestionList ideaId={ideaId} suggestions={suggestions.data} versions={versions} />
    </div>
  );
}

/** The Suggestions pane's footer: where the next step happens. */
export function SuggestionsPaneFooter() {
  return <PaneFooter meta="Pick an angle in the chat to rescore" />;
}
