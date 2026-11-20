import type { ReactNode } from "react";

import { BandBadge } from "@/components/score/band-badge";
import { ParamBar } from "@/components/score/param-bar";
import { MAX_TOTAL, daysAgoLabel, type ScoreRun } from "@/lib/scores/view";

interface ScoreCardProps {
  score: ScoreRun;
  /** Refresh buttons, shown under the title row. */
  actions?: ReactNode;
}

/** The verdict: total out of 100, its band, when it was made, and the six rubric parameters. */
export function ScoreCard({ score, actions }: ScoreCardProps) {
  const checked = daysAgoLabel(score.created_at);
  return (
    <section aria-label="Score" className="flex flex-col gap-3 border bg-card p-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-score font-semibold tracking-score tabular-nums">
          {score.total}
          <small className="text-body font-normal text-muted-foreground">
            {" "}
            / {MAX_TOTAL}
            <span className="sr-only"> points</span>
          </small>
        </p>
        <BandBadge band={score.band} />
      </div>
      {checked ? <p className="text-meta text-muted-foreground">Last checked {checked}</p> : null}
      <ul className="flex flex-col gap-0.5">
        {score.params.map((param) => (
          <ParamBar key={param.param} param={param} />
        ))}
      </ul>
      {actions}
    </section>
  );
}
