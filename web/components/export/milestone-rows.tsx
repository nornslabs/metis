"use client";

import { ChevronRight } from "lucide-react";
import { useState } from "react";

import { PreviewRow } from "@/components/export/preview-row";
import { cn } from "@/lib/cn";
import { actionLabel, newAndUpdated } from "@/lib/export/preview-lines";
import type { ExportPreview } from "@/lib/schemas/export";

/** The milestones line of the preview; it opens to the list of milestone names. */
export function MilestoneRows({ milestones }: { milestones: ExportPreview["milestones"] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <PreviewRow label={`Milestones · ${milestones.total}`}>
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="inline-flex items-center gap-1 text-right focus-visible:outline-none focus-visible:underline"
        >
          {newAndUpdated(milestones.create, milestones.update)}
          <ChevronRight size={12} aria-hidden="true" className={cn("transition-transform", open && "rotate-90")} />
        </button>
      </PreviewRow>
      {open ? (
        <ul className="grid gap-0.5 border-b py-1.5 pl-3 text-meta">
          {milestones.items.map((item, index) => (
            <li key={`${index}:${item.name}`} className="flex justify-between gap-3">
              <span className="min-w-0 truncate">{item.name}</span>
              <span className="text-muted-foreground">{actionLabel(item.action)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}
