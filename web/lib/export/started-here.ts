/**
 * Ideas whose export this tab started. Its dialogs open by themselves when the run asks something;
 * after a reload (or for a teammate's run) only the prompt above the composer shows.
 */
let started: ReadonlySet<string> = new Set();

/** Remembers that this tab started an export of the idea. */
export function markExportStartedHere(ideaId: string): void {
  started = new Set(started).add(ideaId);
}

/** True while this tab's export of the idea has not ended. */
export function wasExportStartedHere(ideaId: string): boolean {
  return started.has(ideaId);
}

/** Forgets the idea (its export ended). */
export function clearExportStartedHere(ideaId: string): void {
  const next = new Set(started);
  next.delete(ideaId);
  started = next;
}
