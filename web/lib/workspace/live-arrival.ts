/** Whether an output was absent when the page first loaded it, for one scope (the idea id). */
export interface ArrivalBaseline {
  readonly scope: string;
  readonly absent: boolean;
}

/** The baseline once the first load has settled; kept as it is afterwards, restarted for a new scope. */
export function nextBaseline(
  baseline: ArrivalBaseline | null,
  scope: string,
  settled: boolean,
  present: boolean,
): ArrivalBaseline | null {
  if (baseline?.scope === scope) return baseline;
  return settled ? { scope, absent: !present } : null;
}

/** An output arrived live when it was absent at first load and is present now. */
export function hasArrived(baseline: ArrivalBaseline | null, scope: string, present: boolean): boolean {
  return baseline?.scope === scope && baseline.absent && present;
}

export interface AutoOpenContext {
  /** The panel was already opened by itself for this idea: it opens once. */
  readonly alreadyOpened: boolean;
  /** Under 820px the panel is a full-screen overlay that would cover the question. */
  readonly narrow: boolean;
  /** An open panel stays where the user is; the new tab gets a dot instead. */
  readonly outputOpen: boolean;
}

/** The pane to open by itself for outputs that just arrived live (first of `arrived`), or null. */
export function pickAutoOpen<Pane>(arrived: readonly Pane[], context: AutoOpenContext): Pane | null {
  if (context.alreadyOpened || context.narrow || context.outputOpen) return null;
  return arrived[0] ?? null;
}
