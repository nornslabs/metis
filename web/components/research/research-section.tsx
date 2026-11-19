"use client";

import { ResearchPanel } from "@/components/research/research-panel";
import { Sources } from "@/components/research/sources";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { describeError } from "@/lib/api/errors";
import { useResearch } from "@/lib/api/queries/use-research";

interface ResearchSectionProps {
  ideaId: string;
  /** True once a Researcher step has started: only then are a loading state or an error worth showing. */
  researchStarted: boolean;
}

/** Sources chips and the research block for an idea: empty before research exists, with an error state. */
export function ResearchSection({ ideaId, researchStarted }: ResearchSectionProps) {
  const research = useResearch(ideaId);

  // Before the Researcher starts there is nothing to load: a failure then is not worth an alert.
  if (research.isError && !researchStarted) return null;
  if (research.isError) {
    return (
      <div role="alert" className="flex flex-wrap items-center gap-2 border border-destructive/40 px-2.5 py-1.5">
        <span className="text-control">Could not load the research. {describeError(research.error)}</span>
        <Button type="button" variant="outline" size="sm" className="ml-auto" onClick={() => void research.refetch()}>
          Retry
        </Button>
      </div>
    );
  }
  if (research.isPending) {
    return researchStarted ? <Skeleton aria-label="Loading research" className="h-10 w-full" /> : null;
  }
  if (!research.data) return null;
  return (
    <>
      <Sources view={research.data} />
      <ResearchPanel view={research.data} />
    </>
  );
}
