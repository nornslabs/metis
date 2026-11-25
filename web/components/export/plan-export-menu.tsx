"use client";

import { Download, FileText, Link2, SquareKanban } from "lucide-react";
import { toast } from "sonner";

import { useStartExport } from "@/components/export/use-start-export";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { describeError } from "@/lib/api/errors";
import { downloadPlanMarkdown } from "@/lib/api/export-markdown";
import { useLinearStatus } from "@/lib/api/queries/use-integrations";
import { useRuns } from "@/lib/api/queries/use-runs";
import { isActiveStatus } from "@/lib/events/reducer";
import { linearItemState } from "@/lib/export/menu-state";
import { withOutputPane } from "@/lib/workspace/panes";

interface PlanExportMenuProps {
  ideaId: string;
  /** True when the plan has at least one task. */
  hasTasks: boolean;
}

/** Export for the Plan pane: the plan as Markdown, a share link, and the Linear export. */
export function PlanExportMenu({ ideaId, hasTasks }: PlanExportMenuProps) {
  const { status: linear } = useLinearStatus();
  const runs = useRuns(ideaId);
  const exporter = useStartExport(ideaId);
  const newest = runs.data?.at(-1);
  const linearItem = linearItemState({
    hasPlan: hasTasks,
    linear,
    runActive: newest !== undefined && isActiveStatus(newest.status),
  });

  const download = () =>
    downloadPlanMarkdown(ideaId).catch((error: unknown) =>
      toast.error("Could not download the plan", { description: describeError(error) }),
    );

  const copyShareLink = async () => {
    const path = withOutputPane(window.location.pathname, new URLSearchParams(), "plan");
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${path}`);
      toast.success("Link copied", { description: "It opens for members of this workspace." });
    } catch {
      toast.error("Could not copy the link", { description: "Copy it from the address bar instead." });
    }
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger render={<Button type="button" variant="outline" size="sm" />}>
          <Download size={13} aria-hidden="true" />
          Export
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" side="top" sideOffset={6} className="w-56 p-0.5">
          <DropdownMenuItem onClick={() => void download()}>
            <FileText size={14} aria-hidden="true" />
            Markdown plan
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => void copyShareLink()}>
            <Link2 size={14} aria-hidden="true" />
            Copy share link
          </DropdownMenuItem>
          <DropdownMenuItem disabled={linearItem.disabled || exporter.pending} onClick={exporter.start}>
            <SquareKanban size={14} aria-hidden="true" />
            Linear
            {linearItem.reason ? <span className="ml-auto text-meta text-muted-foreground">{linearItem.reason}</span> : null}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {exporter.error ? (
        <p role="alert" className="basis-full text-meta text-destructive">
          {exporter.error}
        </p>
      ) : null}
    </>
  );
}
