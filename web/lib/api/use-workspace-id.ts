"use client";

import { useSyncExternalStore } from "react";

import { WORKSPACE_CHANGED_EVENT, getWorkspaceId } from "./workspace";

function subscribe(onChange: () => void): () => void {
  window.addEventListener(WORKSPACE_CHANGED_EVENT, onChange);
  return () => window.removeEventListener(WORKSPACE_CHANGED_EVENT, onChange);
}

/** The chosen workspace id, re-rendering when it changes (null on the server and when unset). */
export function useWorkspaceId(): string | null {
  return useSyncExternalStore(subscribe, getWorkspaceId, () => null);
}
