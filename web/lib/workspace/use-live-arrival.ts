"use client";

import { useState } from "react";

import { hasArrived, nextBaseline, type ArrivalBaseline } from "./live-arrival";

export interface LiveArrival {
  /** True once the output was absent when the page first loaded it and has appeared since. */
  arrived: boolean;
  /** Whether the output was absent at first load; null until the first load has settled. */
  startedAbsent: boolean | null;
}

/**
 * Tells an output produced during this page visit from one that was already there when the page
 * loaded: only the former may open the output panel by itself. `scope` (the idea id) restarts the
 * comparison for another idea; `settled` is true once the first load finished.
 */
export function useLiveArrival(scope: string, settled: boolean, present: boolean): LiveArrival {
  const [stored, setStored] = useState<ArrivalBaseline | null>(null);
  // Derived from props during render (React's "adjust state while rendering"), not in an effect.
  const baseline = nextBaseline(stored, scope, settled, present);
  if (baseline !== stored) setStored(baseline);
  return {
    arrived: hasArrived(baseline, scope, present),
    startedAbsent: baseline?.scope === scope ? baseline.absent : null,
  };
}
