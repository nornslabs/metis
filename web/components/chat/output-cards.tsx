"use client";

import { useEffect, useMemo, useRef } from "react";

import { OutputCard } from "@/components/chat/output-card";
import { usePlanOutput } from "@/components/chat/use-plan-output";
import { LoadFailure } from "@/components/panel/load-failure";
import { ScorePaneBody, ScorePaneFooter } from "@/components/panel/score-pane";
import { SuggestionsPaneBody, SuggestionsPaneFooter } from "@/components/panel/suggestions-pane";
import { ResearchPaneBody, ResearchPaneFooter } from "@/components/panel/research-pane";
import { SpecPaneBody, SpecPaneFooter } from "@/components/panel/spec-pane";
import type { PhaseReviewInterrupt } from "@/lib/events/schemas";
import type { PlanSummary } from "@/lib/plan/view";
import { useResearch } from "@/lib/api/queries/use-research";
import { useSpec } from "@/lib/api/queries/use-spec";
import { SourceIndexProvider } from "@/lib/research/source-context";
import { buildSourceIndex, evidenceSources } from "@/lib/research/sources";
import { isLocked } from "@/lib/spec/spec-editor";
import { useSpecEditor, useSpecEditorState } from "@/lib/spec/use-spec-editor";
import { countOf } from "@/lib/text/count";
import { useScoreOutputs } from "@/lib/scores/use-score-outputs";
import { deltaText } from "@/lib/scores/versions";
import { BAND_LABELS, BAND_RANGES, MAX_TOTAL } from "@/lib/scores/view";
import { useRegisterOutput, type PaneOutput } from "@/lib/workspace/output-registry";
import type { OutputPane } from "@/lib/workspace/panes";
import { pickAutoOpen } from "@/lib/workspace/live-arrival";
import { useLiveArrival } from "@/lib/workspace/use-live-arrival";
import { useNarrow } from "@/lib/workspace/use-narrow";
import { useWorkspacePanels } from "@/lib/workspace/workspace-panels";

interface OutputCardsProps {
  ideaId: string;
  ideaTitle: string;
  /** True while a run of this idea can still change (the score's refresh buttons wait for it). */
  runActive: boolean;
  scoringStarted: boolean;
  researchStarted: boolean;
  /** True once the run can have a spec (the Architect started, the spec is awaiting review, or the idea is past it). */
  specStarted: boolean;
  /** True once the run can have phases or a plan (the Planner started, a review is pending, or the idea is past it). */
  planStarted: boolean;
  runId: string;
  runStatus: string;
  /** The `phase_review` interrupt the run waits on, or null. */
  phaseReview: PhaseReviewInterrupt | null;
}

function planMeta(summary: PlanSummary): string {
  return `${countOf(summary.phases, "phase")} · ${summary.points} pts · critical path ${summary.criticalPoints} pts`;
}

const AUTO_OPEN_ORDER = ["score", "suggestions", "spec", "plan"] as const;
type AutoOpenPane = (typeof AUTO_OPEN_ORDER)[number];

/**
 * Opens the output panel by itself once per idea, for the first output produced live. Not when the
 * panel is already open (it stays where the user is), not under 820px (the toggle's dot lights
 * instead), and never moves focus. An output that arrives later, even after the user closed the
 * panel, does not reopen it.
 */
function useAutoOpen(ideaId: string, arrived: Readonly<Record<AutoOpenPane, boolean>>): void {
  const { outputOpen, openOutput } = useWorkspacePanels();
  const narrow = useNarrow();
  const handled = useRef(new Set<string>());
  const openedFor = useRef<string | null>(null);
  useEffect(() => {
    const fresh = AUTO_OPEN_ORDER.filter((pane) => arrived[pane] && !handled.current.has(`${ideaId}:${pane}`));
    if (fresh.length === 0) return;
    for (const pane of fresh) handled.current.add(`${ideaId}:${pane}`);
    const pane = pickAutoOpen(fresh, { alreadyOpened: openedFor.current === ideaId, narrow, outputOpen });
    if (pane === null) return;
    openedFor.current = ideaId;
    openOutput(pane);
  }, [ideaId, arrived, narrow, outputOpen, openOutput]);
}

/**
 * The outputs of a run as one-line cards in the chat, and the registration of their panes in the
 * output panel. The reports never render in the chat. Each pane registers its own body and footer.
 * One numbered source index (research, then the score's evidence) is shared by the Score and
 * Research panes, so a chip means the same source in both.
 */
export function OutputCards({
  ideaId,
  ideaTitle,
  runActive,
  scoringStarted,
  researchStarted,
  specStarted,
  planStarted,
  runId,
  runStatus,
  phaseReview,
}: OutputCardsProps) {
  const { latest, score, suggestions, versions, newestSuggestions } = useScoreOutputs(ideaId);
  const research = useResearch(ideaId, researchStarted);
  const { pane, outputOpen, openOutput } = useWorkspacePanels();
  const spec = useSpec(ideaId, specStarted);
  const specEditor = useSpecEditor(ideaId);
  const specState = useSpecEditorState(specEditor);
  const specData = spec.data;
  useEffect(() => {
    if (specData) specEditor.sync(specData);
  }, [specData, specEditor]);
  // Leaving the page inside the autosave delay must not lose the last edit (best effort).
  useEffect(() => {
    const flush = () => void specEditor.flush();
    window.addEventListener("pagehide", flush);
    return () => window.removeEventListener("pagehide", flush);
  }, [specEditor]);

  const plan = usePlanOutput({ ideaId, runId, runStatus, planStarted, phaseReview });

  const current = score ? versions.find((version) => version.id === score.id) : undefined;
  const view = research.data ?? null;
  const scoreParams = score?.params;
  // Without research there is no Research pane, so no chip could land anywhere.
  const sourceIndex = useMemo(
    () => buildSourceIndex(view, view && scoreParams ? evidenceSources(scoreParams) : []),
    [view, scoreParams],
  );

  const scoreId = score?.id ?? null;
  const scoreCreatedAt = score?.created_at ?? null;
  const scoreOutput = useMemo<PaneOutput | null>(
    () =>
      scoreId === null || scoreCreatedAt === null
        ? null
        : {
            version: scoreId,
            count: versions.length > 0 ? String(versions.length) : undefined,
            body: (
              <SourceIndexProvider index={sourceIndex}>
                <ScorePaneBody ideaId={ideaId} />
              </SourceIndexProvider>
            ),
            footer: <ScorePaneFooter ideaId={ideaId} ideaTitle={ideaTitle} runActive={runActive} createdAt={scoreCreatedAt} />,
          },
    [scoreId, scoreCreatedAt, versions.length, ideaId, ideaTitle, runActive, sourceIndex],
  );
  const advisedRunId = newestSuggestions[0]?.score_run_id ?? null;
  const suggestionsOutput = useMemo<PaneOutput | null>(
    () =>
      advisedRunId === null
        ? null
        : {
            version: advisedRunId,
            count: String(newestSuggestions.length),
            body: <SuggestionsPaneBody ideaId={ideaId} />,
            footer: <SuggestionsPaneFooter />,
          },
    [advisedRunId, newestSuggestions.length, ideaId],
  );
  const researchOutput = useMemo<PaneOutput | null>(
    () =>
      view === null
        ? null
        : {
            version: view.id,
            count: String(sourceIndex.entries.length),
            body: (
              <SourceIndexProvider index={sourceIndex}>
                <ResearchPaneBody view={view} />
              </SourceIndexProvider>
            ),
            footer: <ResearchPaneFooter ideaTitle={ideaTitle} entries={sourceIndex.entries} />,
          },
    [view, sourceIndex, ideaTitle],
  );
  useRegisterOutput("score", scoreOutput, ideaId);
  useRegisterOutput("suggestions", suggestionsOutput, ideaId);
  const specNumber = specState.latest?.number ?? null;
  const specId = specState.latest?.id ?? null;
  const specLocked = isLocked(specState);
  const specOutput = useMemo<PaneOutput | null>(
    () =>
      specNumber === null || specId === null
        ? null
        : {
            version: specId,
            count: specLocked ? `v${specNumber} ✓` : `v${specNumber}`,
            body: <SpecPaneBody ideaId={ideaId} />,
            footer: <SpecPaneFooter ideaId={ideaId} />,
          },
    [specNumber, specId, specLocked, ideaId],
  );
  useRegisterOutput("research", researchOutput, ideaId);
  useRegisterOutput("spec", specOutput, ideaId);

  // Live outputs open the panel once. The suggestions count as live too when the score was.
  const scoreLive = useLiveArrival(ideaId, !latest.isPending, score !== null);
  const suggestionsLive = useLiveArrival(ideaId, suggestions.data !== undefined, newestSuggestions.length > 0);
  const scoreWasLive = scoreLive.startedAbsent === true;
  const suggestionsSettled = suggestionsLive.startedAbsent !== null;
  const suggestionsArrived = newestSuggestions.length > 0 && (suggestionsLive.arrived || (scoreWasLive && suggestionsSettled));
  const specLive = useLiveArrival(ideaId, specData !== undefined, specData?.latest != null);
  const arrived = useMemo(
    () => ({ score: scoreLive.arrived, suggestions: suggestionsArrived, spec: specLive.arrived, plan: plan.arrived }),
    [scoreLive.arrived, suggestionsArrived, specLive.arrived, plan.arrived],
  );
  useAutoOpen(ideaId, arrived);

  const isOpen = (name: OutputPane) => outputOpen && pane === name;
  const scoreMeta = [
    current ? `v${current.number}` : null,
    current ? deltaText(current.delta) : null,
    score ? `${BAND_LABELS[score.band]} · ${BAND_RANGES[score.band]}` : null,
  ]
    .filter((part): part is string => part !== null)
    .join(" · ");

  return (
    <>
      {latest.isError && scoringStarted ? (
        <LoadFailure what="score" error={latest.error} onRetry={() => void latest.refetch()} />
      ) : null}
      {research.isError && researchStarted ? (
        <LoadFailure what="research" error={research.error} onRetry={() => void research.refetch()} />
      ) : null}
      {score ? (
        <OutputCard pane="score" title={`Score ${score.total} / ${MAX_TOTAL}`} meta={scoreMeta} open={isOpen("score")} onOpen={openOutput} />
      ) : null}
      {newestSuggestions.length > 0 ? (
        <OutputCard
          pane="suggestions"
          title="Suggestions"
          meta={`${countOf(newestSuggestions.length, "way")} to improve`}
          open={isOpen("suggestions")}
          onOpen={openOutput}
        />
      ) : null}
      {view ? (
        <OutputCard
          pane="research"
          title="Research"
          meta={`${countOf(sourceIndex.entries.length, "source")} · ${countOf(view.competitors.length, "competitor")}`}
          open={isOpen("research")}
          onOpen={openOutput}
        />
      ) : null}
      {specNumber !== null ? (
        <OutputCard
          pane="spec"
          title={specLocked ? `Spec v${specNumber}` : `Spec draft v${specNumber}`}
          meta={specLocked ? "Confirmed" : specState.latest?.source === "user" ? "Draft · edited" : "Draft"}
          open={isOpen("spec")}
          onOpen={openOutput}
        />
      ) : null}
      {plan.present ? (
        <OutputCard
          pane="plan"
          title={plan.view ? `Plan · ${countOf(plan.view.summary.tasks, "task")}` : `Phases · ${plan.phaseCount}`}
          meta={plan.view ? planMeta(plan.view.summary) : "Review"}
          open={isOpen("plan")}
          onOpen={openOutput}
        />
      ) : null}
    </>
  );
}
