"use client";

import { ConfirmSpecDialog } from "@/components/spec/confirm-spec-dialog";
import { Button } from "@/components/ui/button";
import type { SpecReviewInterrupt } from "@/lib/events/schemas";
import { useConfirmSpec } from "@/lib/spec/use-confirm-spec";
import { useSpecEditor, useSpecEditorState } from "@/lib/spec/use-spec-editor";

interface SpecReviewPromptProps {
  ideaId: string;
  interrupt: SpecReviewInterrupt;
  onOpenSpec: () => void;
}

/** The run waits for the spec: confirm it here (same as the pane's footer) or open the pane to read and edit it. */
export function SpecReviewPrompt({ ideaId, interrupt, onOpenSpec }: SpecReviewPromptProps) {
  const editor = useSpecEditor(ideaId);
  const state = useSpecEditorState(editor);
  const { open, setOpen, blockedReason, confirm } = useConfirmSpec(editor, state);
  const number = state.latest?.number ?? interrupt.number;

  return (
    <div role="group" aria-label="Review the spec" className="flex flex-col gap-2 border px-2.5 py-2">
      <p className="text-control text-muted-foreground">The spec draft is ready. Review it, then confirm to plan the phases.</p>
      <div className="flex flex-wrap gap-1.5">
        <Button type="button" size="sm" disabled={blockedReason !== null} title={blockedReason ?? undefined} onClick={() => setOpen(true)}>
          {`Confirm spec v${number}`}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onOpenSpec}>
          Open the spec
        </Button>
      </div>
      <ConfirmSpecDialog open={open} onOpenChange={setOpen} number={number} onConfirm={confirm} />
    </div>
  );
}
