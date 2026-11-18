"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, describeError } from "@/lib/api/errors";
import { useCancelRun } from "@/lib/api/mutations/use-cancel-run";
import { newIdempotencyKey, useStartRun } from "@/lib/api/mutations/use-start-run";
import { queryKeys } from "@/lib/api/queries/keys";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

const ALREADY_RUNNING = "run.already_running";
const ALREADY_RUNNING_MESSAGE = "A run is already in progress for this idea.";

/** Refetches the idea and its latest run (both keys start with `queryKeys.idea`). */
export function useRefreshIdea(ideaId: string): () => Promise<void> {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.idea(workspaceId, ideaId) });
}

/**
 * Start / Retry: a new run with a new idempotency key, then the page follows the new latest run.
 * A `409 run.already_running` shows inline and also refetches, so the page picks up that run.
 */
export function useStartRunAction(ideaId: string) {
  const startRun = useStartRun();
  const refresh = useRefreshIdea(ideaId);
  const [error, setError] = useState<string | null>(null);

  const start = () => {
    setError(null);
    startRun.mutate(
      { ideaId, idempotencyKey: newIdempotencyKey() },
      {
        onSuccess: () => void refresh(),
        onError: (error) => {
          const alreadyRunning = error instanceof ApiError && error.code === ALREADY_RUNNING;
          setError(alreadyRunning ? ALREADY_RUNNING_MESSAGE : describeError(error));
          if (alreadyRunning) void refresh();
        },
      },
    );
  };

  return { start, pending: startRun.isPending, error };
}

/**
 * Stop. `cancelled` is done at once (the stream reports it too); `running` means the worker stops
 * at its next step, so the button reads "Stopping…" until the stream reports the end.
 */
export function useStopRunAction(runId: string) {
  const cancelRun = useCancelRun();
  const [workerStopping, setWorkerStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stop = () => {
    setError(null);
    cancelRun.mutate(runId, {
      onSuccess: (result) => setWorkerStopping(result.status === "running"),
      onError: (caught) => setError(describeError(caught)),
    });
  };

  return { stop, stopping: workerStopping || cancelRun.isPending, error };
}
