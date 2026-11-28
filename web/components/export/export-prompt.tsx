"use client";

import { useState } from "react";

import { ExportPreviewDialog } from "@/components/export/export-preview-dialog";
import { TeamPickerDialog } from "@/components/export/team-picker-dialog";
import { useRefreshIdea } from "@/components/chat/use-run-actions";
import { Button } from "@/components/ui/button";
import { describeError } from "@/lib/api/errors";
import { useResumeRun } from "@/lib/api/mutations/use-resume-run";
import { clearExportStartedHere, wasExportStartedHere } from "@/lib/export/started-here";
import type { ExportInterrupt } from "@/lib/events/schemas";
import { exportDecisionSchema, teamChoiceSchema } from "@/lib/schemas/export";

interface ExportPromptProps {
  ideaId: string;
  runId: string;
  interrupt: ExportInterrupt;
}

const INVALID_ANSWER = "That answer could not be sent. Try again.";

const COPY = {
  choose_team: {
    text: "Choose the Linear team for this plan.",
    open: "Choose a team",
    sent: "Team chosen. Building the preview…",
  },
  export_approval: {
    text: "The export preview is ready. Review it, then approve.",
    open: "Review the export",
    sent: "Sent.",
  },
} as const;

/**
 * The prompt above the composer for the two export pauses, and their dialog. The dialog opens by
 * itself only when this tab started the export; Esc closes it without answering and the prompt's
 * button opens it again. Only the dialog's buttons answer the run. The parent keys it by the pause,
 * so each new pause starts with its own open state.
 */
export function ExportPrompt({ ideaId, runId, interrupt }: ExportPromptProps) {
  const [open, setOpen] = useState(() => wasExportStartedHere(ideaId));
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Kept here, not in the dialog, so closing the dialog with Esc does not lose an edit.
  const [projectName, setProjectName] = useState(() =>
    interrupt.kind === "export_approval" ? interrupt.preview.project.name : "",
  );
  const resume = useResumeRun();
  const refresh = useRefreshIdea(ideaId);
  const copy = COPY[interrupt.kind];

  const answer = (value: { team_id: string } | { approved: boolean; project_name?: string }, onSent: () => void) => {
    setError(null);
    resume.mutate(
      { runId, value },
      {
        onSuccess: () => {
          setSent(true);
          setOpen(false);
          onSent();
          void refresh();
        },
        onError: (failure) => setError(describeError(failure)),
      },
    );
  };

  const choose = (teamId: string) => {
    const value = teamChoiceSchema.safeParse({ team_id: teamId });
    if (value.success) answer(value.data, () => undefined);
    else setError(INVALID_ANSWER);
  };
  const decide = (approved: boolean) => {
    const value = exportDecisionSchema.safeParse(approved ? { approved, project_name: projectName } : { approved });
    if (value.success) answer(value.data, () => (approved ? undefined : clearExportStartedHere(ideaId)));
    else setError(INVALID_ANSWER);
  };

  if (sent) {
    return (
      <p role="status" className="border px-2.5 py-2 text-control text-muted-foreground">
        {interrupt.kind === "choose_team" ? copy.sent : "Sent. Waiting for the export…"}
      </p>
    );
  }
  return (
    <div role="group" aria-label="Linear export" className="flex flex-col gap-2 border px-2.5 py-2">
      <p className="text-control text-muted-foreground">{copy.text}</p>
      {error && !open ? (
        <p role="alert" className="text-meta text-destructive">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-1.5">
        <Button type="button" size="sm" onClick={() => setOpen(true)}>
          {copy.open}
        </Button>
      </div>
      {interrupt.kind === "choose_team" ? (
        <TeamPickerDialog
          interrupt={interrupt}
          open={open}
          onOpenChange={setOpen}
          pending={resume.isPending}
          error={error}
          onChoose={choose}
        />
      ) : (
        <ExportPreviewDialog
          ideaId={ideaId}
          interrupt={interrupt}
          name={projectName}
          onNameChange={setProjectName}
          open={open}
          onOpenChange={setOpen}
          pending={resume.isPending}
          error={error}
          onDecide={decide}
        />
      )}
    </div>
  );
}
