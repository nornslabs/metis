"use client";

import { useMemo, type ReactNode } from "react";

import { OutputCard } from "@/components/chat/output-card";
import { ResearchSection } from "@/components/research/research-section";
import { ScoreSection } from "@/components/score/score-section";
import { Button } from "@/components/ui/button";
import { describeError } from "@/lib/api/errors";
import { useLatestScore } from "@/lib/api/queries/use-latest-score";
import { useResearch } from "@/lib/api/queries/use-research";
import { countOf } from "@/lib/text/count";
import { BAND_LABELS, BAND_RANGES, MAX_TOTAL } from "@/lib/scores/view";
import type { OutputPane } from "@/lib/workspace/panes";
import { useRegisterOutput } from "@/lib/workspace/output-registry";
import { useWorkspacePanels } from "@/lib/workspace/workspace-panels";

interface OutputCardsProps {
  ideaId: string;
  /** True while a run of this idea can still change (the score's refresh buttons wait for it). */
  runActive: boolean;
  scoringStarted: boolean;
  researchStarted: boolean;
}

function PaneBody({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-3 p-4">{children}</div>;
}

function LoadFailure({ what, error, onRetry }: { what: string; error: unknown; onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-2 border border-destructive/40 px-2.5 py-1.5">
      <span className="text-control">
        Could not load the {what}. {describeError(error)}
      </span>
      <Button type="button" variant="outline" size="sm" className="ml-auto" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}

/**
 * The outputs of a run as one-line cards in the chat. The report itself lives in the output panel:
 * until the panes have their own components (SHIP-290 and later), the existing score and research
 * views are registered as the panes' content.
 */
export function OutputCards({ ideaId, runActive, scoringStarted, researchStarted }: OutputCardsProps) {
  const latest = useLatestScore(ideaId);
  const research = useResearch(ideaId, researchStarted);
  const { pane, outputOpen, openOutput } = useWorkspacePanels();

  const score = latest.data ?? null;
  const view = research.data ?? null;
  const hasScore = score !== null;
  const hasResearch = view !== null;

  const scoreContent = useMemo(
    () =>
      hasScore ? (
        <PaneBody>
          <ScoreSection ideaId={ideaId} runActive={runActive} scoringStarted={scoringStarted} />
        </PaneBody>
      ) : null,
    [hasScore, ideaId, runActive, scoringStarted],
  );
  const researchContent = useMemo(
    () =>
      hasResearch ? (
        <PaneBody>
          <ResearchSection ideaId={ideaId} researchStarted={researchStarted} />
        </PaneBody>
      ) : null,
    [hasResearch, ideaId, researchStarted],
  );
  useRegisterOutput("score", scoreContent, ideaId);
  useRegisterOutput("research", researchContent, ideaId);

  const isOpen = (name: OutputPane) => outputOpen && pane === name;
  return (
    <>
      {latest.isError && scoringStarted ? (
        <LoadFailure what="score" error={latest.error} onRetry={() => void latest.refetch()} />
      ) : null}
      {research.isError && researchStarted ? (
        <LoadFailure what="research" error={research.error} onRetry={() => void research.refetch()} />
      ) : null}
      {score ? (
        <OutputCard
          pane="score"
          title={`Score ${score.total} / ${MAX_TOTAL}`}
          meta={`${BAND_LABELS[score.band]} · ${BAND_RANGES[score.band]}`}
          open={isOpen("score")}
          onOpen={openOutput}
        />
      ) : null}
      {view ? (
        <OutputCard
          pane="research"
          title="Research"
          meta={`${countOf(view.items.length, "source")} · ${countOf(view.competitors.length, "competitor")}`}
          open={isOpen("research")}
          onOpen={openOutput}
        />
      ) : null}
    </>
  );
}
