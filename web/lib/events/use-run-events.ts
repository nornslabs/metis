"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { useWorkspaceId } from "@/lib/api/use-workspace-id";

import { initialRunState, isTerminalStatus, runReducer, type RunSeed, type RunState } from "./reducer";
import { RUN_EVENT_TYPES, parseRunEvent } from "./schemas";

/** `live` while events flow, `reconnecting` while the browser retries, `ended` after a terminal status. */
export type StreamState = "connecting" | "live" | "reconnecting" | "ended" | "failed";

export type RunEventsResult = {
  state: RunState;
  stream: StreamState;
  /** Catches the state up with a fresh run view (the polling safety net, see `useRunSync`). */
  sync: (view: RunSeed) => void;
};

/** The stream URL. `EventSource` sends no headers, so the workspace goes in the query. */
export function runEventsUrl(runId: string, workspaceId: string | null): string {
  const path = `/v1/runs/${encodeURIComponent(runId)}/events`;
  return workspaceId ? `${path}?workspace_id=${encodeURIComponent(workspaceId)}` : path;
}

/**
 * Follows one run's events (`GET /v1/runs/{id}/events`) with the session cookie. The state starts
 * from the run view (`seed`) and every valid event goes through `runReducer`; the stream replays
 * from the start, and the browser resends `Last-Event-ID` on reconnect, so nothing repeats. The
 * source closes after a terminal `run_status` or a server `error` frame; `onEnd` runs then (and
 * when the browser gives up), so the caller can refetch. Mount it under `key={runId}`: a new run
 * needs a new hook instance (key it by workspace too: a reopened stream replays from the start).
 */
export function useRunEvents(runId: string, seed: RunSeed, onEnd?: () => void): RunEventsResult {
  const [state, dispatch] = useReducer(runReducer, seed, initialRunState);
  const [stream, setStream] = useState<StreamState>("connecting");
  const workspaceId = useWorkspaceId();
  const onEndRef = useRef(onEnd);
  const sync = useCallback((view: RunSeed) => dispatch({ type: "sync", seed: view }), []);

  useEffect(() => {
    onEndRef.current = onEnd;
  }, [onEnd]);

  // Guards against dispatching events after unmount (navigation between ideas).
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    const source = new EventSource(runEventsUrl(runId, workspaceId), { withCredentials: true });
    const end = (stream: StreamState) => {
      source.close();
      setStream(stream);
      onEndRef.current?.();
    };

    const onFrame = (message: MessageEvent<string>) => {
      if (!mountedRef.current) return;
      const event = parseRunEvent(message.type, message.data);
      if (!event) return;
      dispatch(event);
      if (event.type === "run_status" && isTerminalStatus(event.status)) end("ended");
    };

    // `event: error` is the server's frame (a MessageEvent with data); a bare Event is the
    // connection dropping, which the browser retries unless it gave up (CLOSED).
    const onError = (event: Event) => {
      if (!mountedRef.current) return;
      if (event instanceof MessageEvent || source.readyState === EventSource.CLOSED) {
        end("failed");
        return;
      }
      setStream("reconnecting");
    };

    source.onopen = () => {
      if (mountedRef.current) setStream("live");
    };
    source.addEventListener("error", onError);
    for (const type of RUN_EVENT_TYPES) source.addEventListener(type, onFrame);

    return () => {
      mountedRef.current = false;
      source.close();
    };
  }, [runId, workspaceId]);

  return { state, stream, sync };
}
