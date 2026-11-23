"use client";

import { useParams } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useIdea } from "@/lib/api/queries/use-idea";
import { stageLabel } from "@/lib/events/labels";

function Slash() {
  return (
    <span aria-hidden="true" className="opacity-50">
      /
    </span>
  );
}

function IdeaCrumb({ ideaId }: { ideaId: string }) {
  const idea = useIdea(ideaId);
  // The crumb is decorative: when the idea cannot load, the page itself shows the error.
  if (idea.isError) return null;

  return (
    <div className="flex min-w-0 items-center gap-2 text-control text-muted-foreground">
      <Slash />
      {idea.data ? (
        <>
          <span className="max-w-crumb truncate font-medium text-foreground max-guides:max-w-crumb-narrow">
            {idea.data.title}
          </span>
          <Badge
            variant="outline"
            aria-label={`Stage: ${stageLabel(idea.data.stage)}`}
            className="h-badge gap-1.5 px-1.5 text-meta font-normal max-narrow:hidden"
          >
            <span aria-hidden="true" className="size-1.5 bg-muted-foreground" />
            {stageLabel(idea.data.stage)}
          </Badge>
        </>
      ) : (
        <Skeleton className="h-4 w-32" />
      )}
    </div>
  );
}

/** `/ idea title` and the stage after the brand; only on an idea's page, empty on `/`. */
export function HeaderCrumb() {
  const { ideaId } = useParams<{ ideaId?: string }>();
  return ideaId ? <IdeaCrumb ideaId={ideaId} /> : null;
}
