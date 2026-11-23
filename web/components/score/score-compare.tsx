"use client";

import { useState } from "react";

import { SectionHeading } from "@/components/score/section-heading";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { describeError } from "@/lib/api/errors";
import { useScoreRun } from "@/lib/api/queries/use-score-run";
import { compareScores, formatDelta, inOrder } from "@/lib/scores/diff";
import type { ScoreVersion } from "@/lib/scores/versions";
import { BAND_LABELS, formatDay } from "@/lib/scores/view";

const PICK_LIMIT = 2;

function Comparison({ ideaId, ids }: { ideaId: string; ids: readonly [string, string] }) {
  const first = useScoreRun(ideaId, ids[0]);
  const second = useScoreRun(ideaId, ids[1]);
  const error = first.error ?? second.error;
  if (error) return <p role="alert" className="text-control text-destructive">Could not load the scores. {describeError(error)}</p>;
  if (!first.data || !second.data) return <Skeleton aria-label="Loading comparison" className="h-16 w-full" />;
  const [before, after] = inOrder(first.data, second.data);
  const { totalDelta, changes } = compareScores(before, after);
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-control">
        {formatDay(before.created_at)} → {formatDay(after.created_at)}: {before.total} → {after.total} ({formatDelta(totalDelta)})
      </p>
      <ul className="flex flex-col gap-1.5">
        {changes.map((change) => (
          <li key={change.param} className="flex flex-col gap-0.5 border px-2.5 py-1.5">
            <p className="flex items-baseline justify-between gap-2 text-control">
              <span className="font-medium">{change.label}</span>
              <span className="tabular-nums">
                {change.before} → {change.after} <span className="font-medium">({formatDelta(change.delta)})</span>
              </span>
            </p>
            <p className="text-meta break-words text-muted-foreground">Before: {change.beforeReason}</p>
            <p className="text-meta break-words text-muted-foreground">After: {change.afterReason}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The score versions, newest first, with a checkbox each: pick two and compare them parameter by parameter. */
export function ScoreCompare({ ideaId, versions }: { ideaId: string; versions: readonly ScoreVersion[] }) {
  const [picked, setPicked] = useState<readonly string[]>([]);
  const [shown, setShown] = useState<readonly [string, string] | null>(null);
  if (versions.length < PICK_LIMIT) return null;

  const toggle = (id: string) => {
    setShown(null);
    setPicked((current) => (current.includes(id) ? current.filter((known) => known !== id) : [...current, id].slice(-PICK_LIMIT)));
  };
  const [first, second] = picked;
  const pair = first !== undefined && second !== undefined ? ([first, second] as const) : null;

  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend><SectionHeading>Compare two scores</SectionHeading></legend>
      <ul className="flex flex-col">
        {versions.map((version) => (
          <li key={version.id}>
            <label className="flex cursor-pointer items-center gap-2 py-0.5 text-control">
              <input type="checkbox" checked={picked.includes(version.id)} onChange={() => toggle(version.id)} />
              <span className="w-6 font-mono text-meta text-muted-foreground">v{version.number}</span>
              <span className="min-w-0 flex-1 truncate">{version.note}</span>
              <span className="font-medium tabular-nums">{version.total}</span>
              <span className="sr-only">{BAND_LABELS[version.band]}</span>
              <span className="text-meta text-muted-foreground">{formatDay(version.createdAt)}</span>
            </label>
          </li>
        ))}
      </ul>
      <div>
        <Button type="button" variant="outline" size="sm" disabled={pair === null} onClick={() => setShown(pair)}>
          Compare
        </Button>
      </div>
      {shown ? <Comparison ideaId={ideaId} ids={shown} /> : null}
    </fieldset>
  );
}
