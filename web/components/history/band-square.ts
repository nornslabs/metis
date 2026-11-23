import type { ScoreBand } from "@/lib/scores/view";

/** The small square before a score, tinted by band (`bg-muted-foreground` stays for an unscored idea). */
export const BAND_SQUARE: Readonly<Record<ScoreBand, string>> = {
  build: "bg-success",
  promising: "bg-warning",
  advise: "bg-destructive",
};
