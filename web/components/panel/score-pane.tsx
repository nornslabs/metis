"use client";

import { LoadFailure } from "@/components/panel/load-failure";
import { ExportMenu } from "@/components/panel/export-menu";
import { PaneFooter } from "@/components/panel/pane-footer";
import { PaneSection } from "@/components/panel/pane-section";
import { ParamBar } from "@/components/score/param-bar";
import { RefreshActions } from "@/components/score/refresh-actions";
import { ScoreCompare } from "@/components/score/score-compare";
import { ScoreHead } from "@/components/score/score-head";
import { ScoreHistoryChart } from "@/components/score/score-history-chart";
import { Skeleton } from "@/components/ui/skeleton";
import { useScoreOutputs } from "@/lib/scores/use-score-outputs";
import { updatedAgoLabel } from "@/lib/scores/view";

/** The Score pane's body: the verdict, the six rubric rows, and the history with compare. */
export function ScorePaneBody({ ideaId }: { ideaId: string }) {
  const { latest, history, versions } = useScoreOutputs(ideaId);

  if (latest.isError) return <LoadFailure what="score" error={latest.error} onRetry={() => void latest.refetch()} className="m-4" />;
  if (!latest.data) return <Skeleton aria-label="Loading score" className="m-4 h-32" />;

  const score = latest.data;
  return (
    <>
      <ScoreHead score={score} version={versions.find((version) => version.id === score.id)} />
      <PaneSection heading="Rubric" aside="weight · score">
        <ul className="flex flex-col gap-0.5">
          {score.params.map((param) => (
            <ParamBar key={param.param} param={param} />
          ))}
        </ul>
      </PaneSection>
      <PaneSection heading="History">
        {history.data ? (
          <>
            <ScoreHistoryChart history={history.data} />
            {versions.length < 2 ? (
              <p className="text-control text-muted-foreground">One score so far.</p>
            ) : (
              <ScoreCompare ideaId={ideaId} versions={versions} />
            )}
          </>
        ) : (
          <Skeleton aria-label="Loading history" className="h-16" />
        )}
      </PaneSection>
    </>
  );
}

interface ScorePaneFooterProps {
  ideaId: string;
  ideaTitle: string;
  /** True while a run of this idea can still change (the refresh buttons wait for it). */
  runActive: boolean;
  /** When the shown score was made. */
  createdAt: string;
}

/** The Score pane's footer: Export, Re-check market and Rescore. */
export function ScorePaneFooter({ ideaId, ideaTitle, runActive, createdAt }: ScorePaneFooterProps) {
  const updated = updatedAgoLabel(createdAt);
  return (
    <PaneFooter meta={updated ? `Updated ${updated}` : undefined}>
      <ExportMenu ideaId={ideaId} ideaTitle={ideaTitle} />
      <RefreshActions ideaId={ideaId} runActive={runActive} />
    </PaneFooter>
  );
}
