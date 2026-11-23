import { BandBadge } from "@/components/score/band-badge";
import { cn } from "@/lib/cn";
import { deltaText, type ScoreVersion } from "@/lib/scores/versions";
import { MAX_TOTAL, type ScoreRun } from "@/lib/scores/view";

interface ScoreHeadProps {
  score: ScoreRun;
  /** The score's place in the history; absent while the history loads. */
  version: ScoreVersion | undefined;
}

/** The verdict: total (40px) with `/ 100`, the band, "vN · note" and the change from the version before. */
export function ScoreHead({ score, version }: ScoreHeadProps) {
  const delta = version ? deltaText(version.delta) : null;
  const improved = (version?.delta ?? 0) > 0;
  return (
    <section aria-label="Score" className="flex items-end justify-between gap-3 border-b px-4 py-3.5">
      <p className="text-total leading-none font-semibold tracking-score tabular-nums">
        {score.total}
        <small className="text-body font-normal tracking-normal text-muted-foreground">
          {" "}
          / {MAX_TOTAL}
          <span className="sr-only"> points</span>
        </small>
      </p>
      <div className="flex flex-col items-end gap-1.5 text-meta text-muted-foreground">
        <BandBadge band={score.band} />
        {version ? (
          <span>
            v{version.number} · {version.note}
          </span>
        ) : null}
        {delta && version ? (
          <span className={cn("font-mono", improved ? "text-success" : "text-destructive")}>
            {delta} from v{version.number - 1}
          </span>
        ) : null}
      </div>
    </section>
  );
}
