"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

interface RunActivity {
  /** The idea whose run is working right now (a step is active), or null. */
  busyIdeaId: string | null;
  setBusyIdeaId: (ideaId: string | null) => void;
}

const RunActivityContext = createContext<RunActivity | null>(null);

/** Tells the history panel which idea has a run step in flight, so switching away can be blocked. */
export function RunActivityProvider({ children }: { children: ReactNode }) {
  const [busyIdeaId, setBusyIdeaId] = useState<string | null>(null);
  const value = useMemo(() => ({ busyIdeaId, setBusyIdeaId }), [busyIdeaId]);
  return <RunActivityContext value={value}>{children}</RunActivityContext>;
}

function useRunActivity(): RunActivity {
  const value = useContext(RunActivityContext);
  if (!value) throw new Error("Run activity hooks must be used inside <RunActivityProvider>");
  return value;
}

/** The idea with a step in flight, or null. */
export function useBusyIdeaId(): string | null {
  return useRunActivity().busyIdeaId;
}

/** Reports whether `ideaId`'s run has a step in flight; clears on unmount. */
export function useReportRunBusy(ideaId: string, busy: boolean): void {
  const { setBusyIdeaId } = useRunActivity();
  useEffect(() => {
    if (!busy) return;
    setBusyIdeaId(ideaId);
    return () => setBusyIdeaId(null);
  }, [ideaId, busy, setBusyIdeaId]);
}
