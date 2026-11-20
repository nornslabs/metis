import { cn } from "@/lib/cn";
import { BAND_LABELS, BAND_RANGES, type ScoreBand } from "@/lib/scores/view";

const BAND_CLASS: Readonly<Record<ScoreBand, string>> = {
  build: "band-build",
  promising: "band-promising",
  advise: "band-advise",
};

/** The band as text ("Promising · 55–74") on its color: the label carries the meaning, not the color. */
export function BandBadge({ band }: { band: ScoreBand }) {
  return (
    <span className={cn("inline-flex h-badge items-center px-2.5 text-note font-medium", BAND_CLASS[band])}>
      {BAND_LABELS[band]} · {BAND_RANGES[band]}
    </span>
  );
}
