"use client";

import { useStartRunAction } from "@/components/chat/use-run-actions";
import { markExportStartedHere } from "@/lib/export/started-here";

/** Starts a run that exports the idea's plan (the Integrator takes over at stage `planning`). */
export function useStartExport(ideaId: string) {
  const { start, pending, error } = useStartRunAction(ideaId);
  return {
    start: () => {
      markExportStartedHere(ideaId);
      start();
    },
    pending,
    error,
  };
}
