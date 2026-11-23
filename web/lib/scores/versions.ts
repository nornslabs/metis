import { PROMISING_FROM, barPercent, type ScoreRunSummary, type Suggestion } from "@/lib/scores/view";

/** One score run seen as a version of the idea's score: v1 is the oldest. */
export interface ScoreVersion {
  readonly id: string;
  /** Position in the history, oldest = 1. */
  readonly number: number;
  /** A short phrase for why the score was made. */
  readonly note: string;
  readonly total: number;
  readonly band: ScoreRunSummary["band"];
  readonly createdAt: string;
  /** Change in total against the previous version; null for v1. */
  readonly delta: number | null;
}

const TRIGGER_NOTES: Readonly<Record<ScoreRunSummary["trigger"], string>> = {
  manual: "rescore",
  scheduled: "scheduled check",
  signal: "market signal",
};

const FIRST_NOTE = "first score";

/** The history (newest first, as the server sends it) as versions, in the same order. */
export function scoreVersions(history: readonly ScoreRunSummary[]): readonly ScoreVersion[] {
  const oldestFirst = [...history].reverse();
  return oldestFirst
    .map((run, index): ScoreVersion => {
      const previous = oldestFirst[index - 1];
      return {
        id: run.id,
        number: index + 1,
        note: previous ? TRIGGER_NOTES[run.trigger] : FIRST_NOTE,
        total: run.total,
        band: run.band,
        createdAt: run.created_at,
        delta: previous ? run.total - previous.total : null,
      };
    })
    .reverse();
}

/** "▲ 7", "▼ 3", or null when there is nothing to show (v1 or an unchanged total). */
export function deltaText(delta: number | null): string | null {
  if (delta === null || delta === 0) return null;
  return delta > 0 ? `▲ ${delta}` : `▼ ${Math.abs(delta)}`;
}

/** A mark under the promising threshold when scaled to 100. */
export function isWeakMark(raw: number): boolean {
  return barPercent(raw) < PROMISING_FROM;
}

/** The number of the version made after the score run `scoreRunId`, or null if it is the newest. */
export function versionAfter(versions: readonly ScoreVersion[], scoreRunId: string): number | null {
  const index = versions.findIndex((version) => version.id === scoreRunId);
  if (index <= 0) return null;
  return versions[index - 1]?.number ?? null;
}

/** "Applied in v3" for an accepted suggestion once a later version exists, else null. */
export function appliedIn(suggestion: Pick<Suggestion, "status" | "score_run_id">, versions: readonly ScoreVersion[]): number | null {
  if (suggestion.status !== "accepted") return null;
  return versionAfter(versions, suggestion.score_run_id);
}
