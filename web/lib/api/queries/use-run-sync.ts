"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import type { RunSeed } from "@/lib/events/reducer";

const POLL_MS = 5_000;

/**
 * Safety net for the live stream: while `active`, reads the run (`GET /v1/runs/{id}`) every few
 * seconds and passes it to `onView`, so a pause the stream never delivered still shows the
 * question and enables the composer. The stream stays the primary source.
 */
export function useRunSync(runId: string, active: boolean, onView: (view: RunSeed) => void) {
  const view = useQuery({
    queryKey: ["run-sync", runId],
    enabled: active,
    refetchInterval: POLL_MS,
    queryFn: async () => bodyOf(await apiClient.GET("/v1/runs/{run_id}", { params: { path: { run_id: runId } } })),
  });
  useEffect(() => {
    if (view.data) onView(view.data);
  }, [view.data, onView]);
}
