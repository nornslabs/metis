import { useSyncExternalStore } from "react";

import type { LiveExport } from "./status";

/**
 * The newest run's export state per idea. The chat page writes it from the live run; the Plan pane
 * (a separate tree) reads it. Snapshots are replaced, never changed, so subscribers see each update.
 */
let snapshots: ReadonlyMap<string, LiveExport> = new Map();
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function sameExport(a: LiveExport | undefined, b: LiveExport): boolean {
  return (
    a !== undefined &&
    a.runId === b.runId &&
    a.status === b.status &&
    a.progress === b.progress &&
    a.finish === b.finish &&
    a.error?.code === b.error?.code &&
    a.error?.message === b.error?.message
  );
}

/** Publishes the idea's live export state (a no-op when nothing changed). */
export function publishLiveExport(ideaId: string, live: LiveExport): void {
  if (sameExport(snapshots.get(ideaId), live)) return;
  snapshots = new Map(snapshots).set(ideaId, live);
  emit();
}

/** Forgets the idea's live export state, e.g. when leaving the idea. */
export function clearLiveExport(ideaId: string): void {
  if (!snapshots.has(ideaId)) return;
  const next = new Map(snapshots);
  next.delete(ideaId);
  snapshots = next;
  emit();
}

/** The idea's live export state, or null before the page saw a run. */
export function useLiveExport(ideaId: string): LiveExport | null {
  return useSyncExternalStore(
    subscribe,
    () => snapshots.get(ideaId) ?? null,
    () => null,
  );
}
