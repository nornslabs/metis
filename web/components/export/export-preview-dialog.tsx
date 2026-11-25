"use client";

import { ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/cn";
import { missingLabels, newAndUpdated } from "@/lib/export/preview-lines";
import type { ExportApprovalInterrupt } from "@/lib/events/schemas";

interface ExportPreviewDialogProps {
  interrupt: ExportApprovalInterrupt;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pending: boolean;
  error: string | null;
  onDecide: (approved: boolean) => void;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b py-1.5 last:border-b-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right">{children}</dd>
    </div>
  );
}

/** What the export will create or update in Linear. Only Cancel and Approve answer; Esc just closes it. */
export function ExportPreviewDialog({ interrupt, open, onOpenChange, pending, error, onDecide }: ExportPreviewDialogProps) {
  const { preview } = interrupt;
  const [showMilestones, setShowMilestones] = useState(false);
  const labelsMissing = missingLabels(preview);
  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent showCloseButton={false} className="sm:max-w-105">
        <DialogHeader>
          <DialogTitle>Export to Linear</DialogTitle>
          <DialogDescription>Nothing is written until you approve.</DialogDescription>
        </DialogHeader>
        <dl className="text-control">
          <Row label="Team">{preview.team.name}</Row>
          <Row label="Project">
            <span className="break-words">{preview.project.name}</span>{" "}
            <span className="text-meta text-muted-foreground">{preview.project.action === "create" ? "new" : "updated"}</span>
          </Row>
          <Row label={`Milestones · ${preview.milestones.total}`}>
            <button
              type="button"
              aria-expanded={showMilestones}
              onClick={() => setShowMilestones((value) => !value)}
              className="inline-flex items-center gap-1 text-right focus-visible:outline-none focus-visible:underline"
            >
              {newAndUpdated(preview.milestones.create, preview.milestones.update)}
              <ChevronRight size={12} aria-hidden="true" className={cn("transition-transform", showMilestones && "rotate-90")} />
            </button>
          </Row>
          {showMilestones ? (
            <ul className="grid gap-0.5 border-b py-1.5 pl-3 text-meta">
              {preview.milestones.items.map((item, index) => (
                <li key={`${index}:${item.name}`} className="flex justify-between gap-3">
                  <span className="min-w-0 truncate">{item.name}</span>
                  <span className="text-muted-foreground">{item.action === "create" ? "new" : "updated"}</span>
                </li>
              ))}
            </ul>
          ) : null}
          <Row label={`Issues · ${preview.issues.total}`}>{newAndUpdated(preview.issues.create, preview.issues.update)}</Row>
          <Row label="Blocked-by links">{preview.blocked_by_links}</Row>
          {preview.labels.total > 0 && labelsMissing !== null ? (
            <Row label={`Labels · ${preview.labels.total}`}>
              {labelsMissing === 0 ? "all exist" : `${labelsMissing} to create`}
            </Row>
          ) : null}
        </dl>
        {error ? (
          <p role="alert" className="text-meta text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button type="button" variant="outline" disabled={pending} onClick={() => onDecide(false)}>
            Cancel
          </Button>
          <Button type="button" disabled={pending} onClick={() => onDecide(true)}>
            {pending ? "Sending…" : "Approve"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
