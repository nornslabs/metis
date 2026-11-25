"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { queryKeys } from "@/lib/api/queries/keys";
import { isTerminalStatus, type RunState } from "@/lib/events/reducer";
import { clearLiveExport, publishLiveExport } from "@/lib/export/live-export";
import { clearExportStartedHere } from "@/lib/export/started-here";

/**
 * Hands the live run's export state to the Plan pane, and when the run ends refreshes the stored
 * result (so the pane and the history badge show it) and forgets that this tab started it.
 */
export function useLiveExportSync(ideaId: string, runId: string, state: RunState): void {
  const queryClient = useQueryClient();
  const { status, exportProgress, exportFinish, error } = state;
  const errorCode = error?.code ?? null;
  const errorMessage = error?.message ?? null;

  useEffect(() => {
    publishLiveExport(ideaId, {
      runId,
      status,
      progress: exportProgress,
      finish: exportFinish,
      error: errorCode !== null && errorMessage !== null ? { code: errorCode, message: errorMessage } : null,
    });
  }, [ideaId, runId, status, exportProgress, exportFinish, errorCode, errorMessage]);

  useEffect(() => {
    if (!isTerminalStatus(status)) return;
    clearExportStartedHere(ideaId);
    void queryClient.invalidateQueries({ queryKey: queryKeys.allExportSummaries() });
  }, [queryClient, ideaId, status]);

  useEffect(() => () => clearLiveExport(ideaId), [ideaId]);
}
