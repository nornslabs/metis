"use client";

import { Download, FileText, Link2, SquareKanban } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { downloadTextFile } from "@/lib/download";
import { buildScoreReport, reportFileName } from "@/lib/scores/report";
import { useScoreOutputs } from "@/lib/scores/use-score-outputs";
import { withOutputPane } from "@/lib/workspace/panes";

interface ExportMenuProps {
  ideaId: string;
  ideaTitle: string;
}

/**
 * Export for the Score pane. Built in the browser: the report is the loaded score as Markdown, and
 * the share link is this idea's URL on the Score pane (it opens for signed-in members only).
 * Linear stays off until a plan exists.
 */
export function ExportMenu({ ideaId, ideaTitle }: ExportMenuProps) {
  const { score, history, versions, newestSuggestions } = useScoreOutputs(ideaId);
  const ready = score !== null && history.data !== undefined;

  const downloadReport = () => {
    if (!score) return;
    downloadTextFile(reportFileName(ideaTitle), buildScoreReport({ ideaTitle, score, versions, suggestions: newestSuggestions }));
  };

  const copyShareLink = async () => {
    const path = withOutputPane(window.location.pathname, new URLSearchParams(), "score");
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${path}`);
      toast.success("Link copied", { description: "It opens for members of this workspace." });
    } catch {
      toast.error("Could not copy the link", { description: "Copy it from the address bar instead." });
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button type="button" variant="outline" size="sm" disabled={!ready} />}>
        <Download size={13} aria-hidden="true" />
        Export
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" sideOffset={6} className="w-52 p-0.5">
        <DropdownMenuItem onClick={downloadReport}>
          <FileText size={14} aria-hidden="true" />
          Markdown report
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => void copyShareLink()}>
          <Link2 size={14} aria-hidden="true" />
          Copy share link
        </DropdownMenuItem>
        <DropdownMenuItem disabled>
          <SquareKanban size={14} aria-hidden="true" />
          Linear
          <span className="ml-auto text-meta text-muted-foreground">after the plan</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
