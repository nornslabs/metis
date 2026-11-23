"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { BAND_SQUARE } from "@/components/history/band-square";
import { ScoreSpark } from "@/components/score/score-spark";
import { useIdeas } from "@/lib/api/queries/use-ideas";
import { useScoreSummaries } from "@/lib/api/queries/use-score-summaries";
import { cn } from "@/lib/cn";
import { stageLabel } from "@/lib/events/labels";
import { relativeTime } from "@/lib/history/relative-time";
import { rowLabel, toHistoryRow, type HistoryRow } from "@/lib/history/rows";
import { useWorkspacePanels } from "@/lib/workspace/workspace-panels";

const RECENT_COUNT = 2;

function RecentRow({ row }: { row: HistoryRow }) {
  return (
    <Link
      href={`/ideas/${row.id}`}
      aria-label={rowLabel(row)}
      className="grid w-full grid-cols-[1fr_auto_auto] items-center gap-x-2.5 gap-y-px px-3 py-2 text-left outline-none transition-colors duration-150 hover:bg-accent focus-visible:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset motion-reduce:transition-none [&+&]:border-t"
    >
      <span className="truncate text-control font-medium">{row.title}</span>
      <span className="col-start-2 row-span-2 row-start-1 flex items-center gap-1.5 text-note font-semibold tabular-nums">
        <ScoreSpark totals={row.totals} />
        <span aria-hidden="true" className={cn("size-1.5 bg-muted-foreground", row.band && BAND_SQUARE[row.band])} />
        <span className={cn(row.score === null && "font-normal text-muted-foreground")}>{row.score ?? "–"}</span>
      </span>
      <ArrowRight aria-hidden="true" className="col-start-3 row-span-2 row-start-1 size-3 text-muted-foreground" />
      <span className="col-start-1 row-start-2 text-meta text-muted-foreground">
        {stageLabel(row.stage)} · {relativeTime(row.activeAt)}
      </span>
    </Link>
  );
}

/**
 * "Pick up where you left off": the two most recent ideas of the workspace, each a link to its
 * conversation, and a button that opens the history panel. Draws nothing while the list loads,
 * fails or is empty, so a first-time user sees only the composer.
 */
export function RecentIdeas() {
  const ideas = useIdeas();
  const { openHistory } = useWorkspacePanels();
  const recent = (ideas.data?.pages[0]?.items ?? []).slice(0, RECENT_COUNT);
  const summaries = useScoreSummaries(recent.map((idea) => idea.id));
  if (recent.length === 0) return null;

  return (
    <section aria-label="Recent ideas" className="mt-5.5 w-full max-w-110 border bg-background text-left short:mt-3.5">
      <div className="flex items-center justify-between border-b px-3 py-1.75 text-meta tracking-label text-muted-foreground uppercase">
        <h2 className="font-normal">Pick up where you left off</h2>
        <button
          type="button"
          onClick={openHistory}
          className="tracking-normal normal-case outline-none transition-colors duration-150 hover:text-foreground hover:underline hover:underline-offset-3 focus-visible:text-foreground focus-visible:underline motion-reduce:transition-none"
        >
          All ideas
        </button>
      </div>
      {recent.map((idea) => (
        <RecentRow key={idea.id} row={toHistoryRow(idea, summaries.get(idea.id))} />
      ))}
    </section>
  );
}
