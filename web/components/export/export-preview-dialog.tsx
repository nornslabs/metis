"use client";

import { HldSection } from "@/components/export/hld-section";
import { IssueBriefList } from "@/components/export/issue-brief-list";
import { MilestoneRows } from "@/components/export/milestone-rows";
import { PreviewRow as Row } from "@/components/export/preview-row";
import { ProjectNameField } from "@/components/export/project-name-field";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { actionLabel, missingLabels, newAndUpdated } from "@/lib/export/preview-lines";
import type { ExportApprovalInterrupt } from "@/lib/events/schemas";
import { projectNameError } from "@/lib/schemas/export";

interface ExportPreviewDialogProps {
  ideaId: string;
  interrupt: ExportApprovalInterrupt;
  name: string;
  onNameChange: (name: string) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pending: boolean;
  error: string | null;
  onDecide: (approved: boolean) => void;
}

/**
 * What the export will create or update in Linear: the editable project name, the issue briefs and
 * the HLD (read only). Only Cancel and Approve answer; Esc just closes it.
 */
export function ExportPreviewDialog({
  ideaId,
  interrupt,
  name,
  onNameChange,
  open,
  onOpenChange,
  pending,
  error,
  onDecide,
}: ExportPreviewDialogProps) {
  const { preview } = interrupt;
  const labelsMissing = missingLabels(preview);
  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent showCloseButton={false} className="sm:max-w-140">
        <DialogHeader>
          <DialogTitle>Export to Linear</DialogTitle>
          <DialogDescription>Nothing is written until you approve.</DialogDescription>
        </DialogHeader>
        <div className="flex max-h-[60vh] flex-col gap-2 overflow-y-auto">
          <ProjectNameField value={name} onChange={onNameChange} disabled={pending} />
          <dl className="text-control">
            <Row label="Team">{preview.team.name}</Row>
            <Row label="Project">{actionLabel(preview.project.action)}</Row>
            <MilestoneRows milestones={preview.milestones} />
            <Row label={`Issues · ${preview.issues.total}`}>
              {newAndUpdated(preview.issues.create, preview.issues.update)}
            </Row>
            <Row label="Blocked-by links">{preview.blocked_by_links}</Row>
            {preview.labels.total > 0 && labelsMissing !== null ? (
              <Row label={`Labels · ${preview.labels.total}`}>
                {labelsMissing === 0 ? "all exist" : `${labelsMissing} to create`}
              </Row>
            ) : null}
          </dl>
          {preview.issues.items.length > 0 ? <IssueBriefList issues={preview.issues.items} /> : null}
          {preview.hld ? <HldSection ideaId={ideaId} hld={preview.hld} /> : null}
        </div>
        {error ? (
          <p role="alert" className="text-meta text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button type="button" variant="outline" disabled={pending} onClick={() => onDecide(false)}>
            Cancel
          </Button>
          <Button type="button" disabled={pending || projectNameError(name) !== null} onClick={() => onDecide(true)}>
            {pending ? "Sending…" : "Approve"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
