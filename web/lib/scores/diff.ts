import { PARAM_LABELS, type ScoreParam, type ScoreRun } from "./view";

export type ParamChange = {
  readonly param: ScoreParam;
  readonly label: string;
  readonly before: number;
  readonly after: number;
  /** `after - before`. */
  readonly delta: number;
  readonly beforeReason: string;
  readonly afterReason: string;
};

export type ScoreComparison = {
  readonly totalDelta: number;
  readonly changes: readonly ParamChange[];
};

/** `+2`, `−1`, `0`: a signed change with a real minus sign. */
export function formatDelta(delta: number): string {
  if (delta === 0) return "0";
  return delta > 0 ? `+${delta}` : `−${Math.abs(delta)}`;
}

/** The per-parameter change from the `before` run to the `after` run, in the `after` run's order. */
export function compareScores(before: ScoreRun, after: ScoreRun): ScoreComparison {
  const earlier = new Map(before.params.map((entry) => [entry.param, entry]));
  const changes = after.params.flatMap((entry): ParamChange[] => {
    const old = earlier.get(entry.param);
    if (!old) return [];
    return [
      {
        param: entry.param,
        label: PARAM_LABELS[entry.param],
        before: old.raw,
        after: entry.raw,
        delta: entry.raw - old.raw,
        beforeReason: old.reason,
        afterReason: entry.reason,
      },
    ];
  });
  return { totalDelta: after.total - before.total, changes };
}

/** Orders two score runs oldest first, whichever order they were picked in. */
export function inOrder<T extends { created_at: string }>(a: T, b: T): readonly [T, T] {
  return new Date(a.created_at).getTime() <= new Date(b.created_at).getTime() ? [a, b] : [b, a];
}
