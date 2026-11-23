"use client";

import { useState, type ReactNode } from "react";

import { PaneFooter } from "@/components/panel/pane-footer";
import { ConfirmSpecDialog } from "@/components/spec/confirm-spec-dialog";
import { ListField, TextField } from "@/components/spec/spec-fields";
import { Button } from "@/components/ui/button";
import { currentMarkdown, isLocked, type SpecEditorState } from "@/lib/spec/spec-editor";
import { visibleSections, type SectionView } from "@/lib/spec/sections";
import { useConfirmSpec } from "@/lib/spec/use-confirm-spec";
import { useSpecEditor, useSpecEditorState } from "@/lib/spec/use-spec-editor";

/** The sections as they were when the text last came from outside; typing never reshuffles them. */
function useSectionSnapshot(state: SpecEditorState): readonly SectionView[] {
  const [snapshot, setSnapshot] = useState<{ epoch: number; ready: boolean; views: readonly SectionView[] } | null>(null);
  const ready = state.latest !== null;
  if (ready && (snapshot === null || !snapshot.ready || snapshot.epoch !== state.epoch)) {
    const views = visibleSections(currentMarkdown(state));
    setSnapshot({ epoch: state.epoch, ready, views });
    return views;
  }
  return snapshot?.views ?? [];
}

function Banner({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="mb-3 flex flex-wrap items-center gap-2 border border-warning bg-card px-2.5 py-2 text-control">
      {children}
    </div>
  );
}

/** The Spec pane's body: the hint, then each section editable in place until the spec is confirmed. */
export function SpecPaneBody({ ideaId }: { ideaId: string }) {
  const editor = useSpecEditor(ideaId);
  const state = useSpecEditorState(editor);
  const views = useSectionSnapshot(state);
  const locked = isLocked(state);

  if (state.latest === null) {
    return <p className="px-4 py-3.5 text-control text-muted-foreground">The spec is not ready yet.</p>;
  }
  return (
    <div className="px-4 py-3.5">
      {locked ? null : (
        <p className="mb-3 text-meta text-muted-foreground">Click any section to edit. Changes save automatically.</p>
      )}
      {state.status === "conflict" ? (
        <Banner>
          <span className="min-w-0 flex-1">
            <b className="font-medium">Spec changed elsewhere.</b> Reload shows the newest version and drops the change that was not saved.
          </span>
          <Button type="button" size="sm" onClick={() => void editor.reload()}>
            Reload
          </Button>
        </Banner>
      ) : null}
      {state.status === "failed" ? (
        <Banner>
          <span className="min-w-0 flex-1">
            <b className="font-medium">Could not save.</b> {state.error} Your text is kept here.
          </span>
          <Button type="button" size="sm" onClick={() => void editor.flush()}>
            Retry
          </Button>
        </Banner>
      ) : null}
      {views.map((view) => (
        <section key={`${state.epoch}:${view.key}`} aria-label={view.label} className="mb-3.5 last:mb-0">
          <h4 className="mb-1 text-control font-semibold">{view.label}</h4>
          {view.kind === "list" ? (
            <ListField
              label={view.label}
              placeholder={view.placeholder}
              locked={locked}
              initial={view.items}
              onChange={(text) => editor.edit(view.key, text)}
            />
          ) : (
            <TextField
              label={view.label}
              placeholder={view.placeholder}
              locked={locked}
              initial={view.text}
              onChange={(text) => editor.edit(view.key, text)}
            />
          )}
        </section>
      ))}
    </div>
  );
}

function statusLine(state: SpecEditorState): ReactNode {
  const { latest, status } = state;
  if (latest === null) return null;
  if (isLocked(state)) return <span className="text-success">{`Confirmed · v${latest.number}`}</span>;
  if (status === "dirty" || status === "saving") return <span className="text-warning">Saving…</span>;
  if (status === "failed") return <span className="text-destructive">Not saved</span>;
  if (status === "conflict") return <span className="text-warning">Spec changed elsewhere</span>;
  const edited = latest.source === "user" ? ", edited" : "";
  return <span className="text-success">{`Saved · draft v${latest.number}${edited}`}</span>;
}

/** The Spec pane's footer: the save state, and Confirm spec (Continue run when a confirmed spec could not resume the run). */
export function SpecPaneFooter({ ideaId }: { ideaId: string }) {
  const editor = useSpecEditor(ideaId);
  const state = useSpecEditorState(editor);
  const { open, setOpen, blockedReason, confirm } = useConfirmSpec(editor, state);
  const locked = isLocked(state);

  return (
    <PaneFooter meta={<span role="status" aria-live="polite">{statusLine(state)}</span>}>
      {locked && state.confirmProblem === "enqueue" ? (
        <Button type="button" size="sm" disabled={state.confirming} onClick={confirm}>
          Continue run
        </Button>
      ) : null}
      {!locked ? (
        <Button
          type="button"
          size="sm"
          disabled={blockedReason !== null}
          title={blockedReason ?? undefined}
          onClick={() => setOpen(true)}
        >
          Confirm spec
        </Button>
      ) : null}
      {state.confirmProblem !== null && state.error ? (
        <span role="alert" className="pt-1.5 text-meta text-destructive">
          {state.confirmProblem === "enqueue" ? "Confirmed, but the run could not continue. Try again." : state.error}
        </span>
      ) : null}
      {state.latest ? (
        <ConfirmSpecDialog open={open} onOpenChange={setOpen} number={state.latest.number} onConfirm={confirm} />
      ) : null}
    </PaneFooter>
  );
}
