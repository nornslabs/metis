"use client";

import { ChevronRight } from "lucide-react";
import { useId, useState } from "react";

import { SafeMarkdown } from "@/components/chat/safe-markdown";
import { cn } from "@/lib/cn";
import { splitAgentNotes } from "@/lib/export/brief";
import type { PreviewIssue } from "@/lib/schemas/export";

function IssueRow({ issue }: { issue: PreviewIssue }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const { body, notes } = splitAgentNotes(issue.description);
  return (
    <li className="border-b last:border-b-0">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 py-1.5 text-left text-control focus-visible:underline focus-visible:outline-none"
      >
        <ChevronRight
          size={12}
          aria-hidden="true"
          className={cn("shrink-0 transition-transform", open && "rotate-90")}
        />
        <span className="min-w-0 flex-1 truncate">{issue.title}</span>
        {issue.component ? (
          <span className="shrink-0 border px-1 text-meta text-muted-foreground">{issue.component}</span>
        ) : null}
      </button>
      {open ? (
        <div id={panelId} className="flex flex-col gap-2 pb-2 pl-5 text-note break-words">
          {body !== "" ? <SafeMarkdown text={body} /> : <p className="text-muted-foreground">No description.</p>}
          {notes !== null ? (
            <section aria-label="Agent notes" className="flex flex-col gap-1 border-l pl-2 text-muted-foreground">
              <h4 className="text-meta font-medium uppercase">Agent notes</h4>
              <SafeMarkdown text={notes} />
            </section>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

/** Every issue the export will write; each row opens to its full brief (sanitized Markdown). */
export function IssueBriefList({ issues }: { issues: readonly PreviewIssue[] }) {
  return (
    <ul aria-label="Issues" className="border-b">
      {issues.map((issue, index) => (
        <IssueRow key={`${index}:${issue.title}`} issue={issue} />
      ))}
    </ul>
  );
}
