"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";

import { PlanPaneBody, PlanPaneFooter } from "@/components/panel/plan-pane";
import { queryKeys } from "@/lib/api/queries/keys";
import { usePlan } from "@/lib/api/queries/use-plan";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";
import type { PhaseReviewInterrupt } from "@/lib/events/schemas";
import { usePhaseReview, usePhaseReviewState } from "@/lib/plan/use-plan-state";
import { buildPlanView, type PlanView } from "@/lib/plan/view";
import { useRegisterOutput, type PaneOutput } from "@/lib/workspace/output-registry";
import { useLiveArrival } from "@/lib/workspace/use-live-arrival";

interface PlanOutputInput {
  ideaId: string;
  runId: string;
  runStatus: string;
  /** True once the run can have phases or a plan (the Planner started, a review is pending, or the idea is past it). */
  planStarted: boolean;
  /** The `phase_review` interrupt the run waits on, or null. */
  phaseReview: PhaseReviewInterrupt | null;
}

export interface PlanOutput {
  /** The plan as the pane reads it, or null while there is none. */
  view: PlanView | null;
  /** Phases in the review (what the card counts before a plan exists). */
  phaseCount: number;
  /** True once the phases or the plan arrived live (the panel may open by itself). */
  arrived: boolean;
  /** True when the pane has anything to show: a review, an approved review waiting for tasks, or a plan. */
  present: boolean;
}

/**
 * Everything the chat needs for the Plan pane: reads the plan, hands the pending review to its
 * store, registers the pane in the output panel, and tells when the output arrived live.
 */
export function usePlanOutput({ ideaId, runId, runStatus, planStarted, phaseReview }: PlanOutputInput): PlanOutput {
  const review = usePhaseReview(ideaId);
  const reviewState = usePhaseReviewState(review);
  const hasActivePlan = planStarted || reviewState.status === "sent" || reviewState.phases.length > 0;
  const plan = usePlan(ideaId, hasActivePlan);
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();
  const proposedPhases = phaseReview?.phases;
  useEffect(() => {
    if (proposedPhases) review.sync(runId, proposedPhases);
  }, [review, runId, proposedPhases]);
  // The Planner saves the plan as the run ends: no event carries it, so read it when the run moves.
  useEffect(() => {
    if (hasActivePlan) void queryClient.invalidateQueries({ queryKey: queryKeys.plan(workspaceId, ideaId) });
  }, [queryClient, workspaceId, ideaId, hasActivePlan, runStatus]);

  const planData = plan.data ?? null;
  const view = useMemo(() => (planData ? buildPlanView(planData) : null), [planData]);
  const reviewing =
    phaseReview !== null ||
    (planData === null && reviewState.runId !== null && reviewState.phases.length > 0 && reviewState.status !== "sent");
  const phaseCount = reviewState.phases.length;
  const planId = planData?.id ?? null;
  const planVersion = planData?.version ?? null;
  const taskCount = view?.summary.tasks ?? null;
  const reviewKey = phaseReview?.text ?? reviewState.runId ?? null;
  const present = planId !== null || reviewing || reviewState.status === "sent";
  const output = useMemo<PaneOutput | null>(() => {
    if (!present) return null;
    return {
      version: planId !== null ? `${planId}:${planVersion}` : `review:${reviewState.runId ?? runId}:${reviewKey}`,
      count: String(taskCount ?? phaseCount),
      body: <PlanPaneBody ideaId={ideaId} reviewing={reviewing} />,
      footer: <PlanPaneFooter ideaId={ideaId} reviewing={reviewing} />,
    };
  }, [present, planId, planVersion, taskCount, reviewing, reviewState.runId, runId, reviewKey, phaseCount, ideaId]);
  useRegisterOutput("plan", output, ideaId);

  const live = useLiveArrival(ideaId, plan.isFetched, present);
  return { view, phaseCount, arrived: live.arrived, present };
}
