"use client";

import { useState } from "react";

import { ExportStatus } from "@/components/export/export-status";
import { PlanExportMenu } from "@/components/export/plan-export-menu";
import { LoadFailure } from "@/components/panel/load-failure";
import { PaneBanner } from "@/components/panel/pane-banner";
import { PaneFooter } from "@/components/panel/pane-footer";
import { PhaseReviewBody, PhaseReviewFooter } from "@/components/plan/phase-review";
import { PlanGraph } from "@/components/plan/plan-graph";
import { PlanSummaryStrip } from "@/components/plan/plan-summary";
import { TaskList, type TaskTarget } from "@/components/plan/task-list";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { usePlan } from "@/lib/api/queries/use-plan";
import { footerStatus, type FooterTone } from "@/lib/plan/footer-status";
import { planMode } from "@/lib/plan/mode";
import { usePhaseReview, usePhaseReviewState, usePlanEditor, usePlanEditorState } from "@/lib/plan/use-plan-state";
import { buildPlanView } from "@/lib/plan/view";
import type { Plan } from "@/lib/schemas/plan";
import { useNarrow } from "@/lib/workspace/use-narrow";

type PlanViewMode = "list" | "graph";

const TONE_CLASS: Readonly<Record<FooterTone, string>> = {
  muted: "",
  success: "text-success",
  warning: "text-warning",
  destructive: "text-destructive",
};

function ViewSwitch({ view, graphDisabled, onChange }: { view: PlanViewMode; graphDisabled: boolean; onChange: (view: PlanViewMode) => void }) {
  const names = graphDisabled ? (["list"] as const) : (["list", "graph"] as const);
  return (
    <div role="group" aria-label="Plan view" className="inline-flex border">
      {names.map((name) => (
        <button
          key={name}
          type="button"
          aria-pressed={view === name}
          onClick={() => onChange(name)}
          className={cn(
            "h-6 w-16 text-meta capitalize not-first:border-l focus-visible:bg-accent focus-visible:outline-none",
            view === name ? "bg-foreground text-background focus-visible:bg-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground",
          )}
        >
          {name}
        </button>
      ))}
    </div>
  );
}

function SaveBanners({ ideaId }: { ideaId: string }) {
  const editor = usePlanEditor(ideaId);
  const state = usePlanEditorState(editor);
  if (state.status === "conflict") {
    return (
      <PaneBanner className="m-4 mb-0">
        <span className="min-w-0 flex-1">
          <b className="font-medium">Plan changed elsewhere.</b> Reload shows the newest plan and drops the change that was not saved.
        </span>
        <Button type="button" size="sm" onClick={() => void editor.reload()}>
          Reload
        </Button>
      </PaneBanner>
    );
  }
  if (state.status === "failed") {
    return (
      <PaneBanner className="m-4 mb-0">
        <span className="min-w-0 flex-1">
          <b className="font-medium">Could not save.</b> {state.error}
        </span>
        <Button type="button" size="sm" onClick={() => void editor.flush()}>
          Retry
        </Button>
      </PaneBanner>
    );
  }
  return null;
}

/** Which tasks are open and which one was asked for (a chip or a graph node), shared by list and graph. */
function useTaskNavigation() {
  const [view, setView] = useState<PlanViewMode>("list");
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const [target, setTarget] = useState<TaskTarget | null>(null);
  const toggle = (taskId: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  // From a chip or a graph node: show the task in the list, open, scrolled to and flashed.
  const go = (taskId: string) => {
    setView("list");
    setOpen((current) => new Set(current).add(taskId));
    setTarget((current) => ({ id: taskId, nonce: (current?.nonce ?? 0) + 1 }));
  };
  return { view, setView, open, target, toggle, go };
}

function PlanBody({ ideaId, plan }: { ideaId: string; plan: Plan }) {
  const editor = usePlanEditor(ideaId);
  const narrow = useNarrow();
  const { view, setView, open, target, toggle, go } = useTaskNavigation();
  const planView = buildPlanView(plan);
  const shown = narrow ? "list" : view;

  return (
    <div>
      <ExportStatus ideaId={ideaId} />
      <SaveBanners ideaId={ideaId} />
      <PlanSummaryStrip summary={planView.summary} />
      <div className="flex items-center justify-between gap-2.5 border-b px-4 py-2">
        <ViewSwitch view={shown} graphDisabled={narrow} onChange={setView} />
        <span className="flex items-center gap-1.5 text-meta text-muted-foreground">
          <i aria-hidden="true" className="size-2.5 border-2 border-foreground" />
          Critical path
        </span>
      </div>
      {shown === "list" ? (
        <TaskList plan={planView} open={open} target={target} locked={plan.status === "ready"} editor={editor} onToggle={toggle} onGo={go} />
      ) : (
        <PlanGraph plan={planView} onOpenTask={go} />
      )}
    </div>
  );
}

interface PlanPaneProps {
  ideaId: string;
  /** The run waits on `phase_review`. */
  reviewing: boolean;
}

/** The pane's mode and plan, read the same way by the body and the footer. */
function usePlanPane({ ideaId, reviewing }: PlanPaneProps) {
  const plan = usePlan(ideaId, true);
  const reviewState = usePhaseReviewState(usePhaseReview(ideaId));
  const mode = planMode({ reviewing, reviewStatus: reviewState.status, plan: plan.isPending ? undefined : plan.data });
  return { plan, mode };
}

/** The Plan pane's body: the phase review, then the plan (list or graph). */
export function PlanPaneBody(props: PlanPaneProps) {
  const { ideaId } = props;
  const { plan, mode } = usePlanPane(props);

  if (mode === "review") return <PhaseReviewBody ideaId={ideaId} />;
  if (plan.isError && !plan.data) {
    return <LoadFailure what="plan" error={plan.error} onRetry={() => void plan.refetch()} className="m-4" />;
  }
  if (mode === "plan" && plan.data) return <PlanBody ideaId={ideaId} plan={plan.data} />;
  if (mode === "planning") {
    return (
      <p role="status" className="px-4 py-3.5 text-control text-muted-foreground">
        Planning tasks…
      </p>
    );
  }
  return <Skeleton aria-label="Loading plan" className="m-4 h-32" />;
}

/** The Plan pane's footer: Approve phases while reviewing, else the save state and plan version. */
export function PlanPaneFooter(props: PlanPaneProps) {
  const { ideaId } = props;
  const { plan, mode } = usePlanPane(props);
  const editorState = usePlanEditorState(usePlanEditor(ideaId));

  if (mode === "review") return <PhaseReviewFooter ideaId={ideaId} />;
  if (mode !== "plan" || !plan.data) return <PaneFooter />;
  const status = footerStatus(plan.data, editorState);
  return (
    <PaneFooter
      meta={
        <span role="status" aria-live="polite" className={TONE_CLASS[status.tone]}>
          {status.text}
        </span>
      }
    >
      <PlanExportMenu ideaId={ideaId} hasTasks={plan.data.phases.some((phase) => phase.tasks.length > 0)} />
    </PaneFooter>
  );
}
