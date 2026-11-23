/**
 * Which version the Spec pane shows. `edit` is the newest version, editable until confirmed;
 * `version` is an older one, read-only; `compare` is the diff of an older version with the newest.
 */
export type SpecView =
  | { readonly mode: "edit" }
  | { readonly mode: "version"; readonly number: number }
  | { readonly mode: "compare"; readonly from: number | null };

const FIRST_VERSION = 1;

export const EDIT_VIEW: SpecView = { mode: "edit" };

/** The view to show given the newest number: showing the newest version is editing it. */
export function resolveView(view: SpecView, latestNumber: number): SpecView {
  if (view.mode === "version" && view.number >= latestNumber) return EDIT_VIEW;
  return view;
}

/** The older version a compare starts from: the chosen one if it is still older, else the one before the newest. */
export function compareFrom(view: SpecView, latestNumber: number): number | null {
  if (latestNumber < MIN_VERSIONS_TO_COMPARE) return null;
  const chosen = view.mode === "compare" ? view.from : null;
  return chosen !== null && chosen >= FIRST_VERSION && chosen < latestNumber ? chosen : latestNumber - 1;
}

/** The fewest versions Compare needs: one to start from and the newest. */
export const MIN_VERSIONS_TO_COMPARE = 2;

/** "v3". */
export function versionLabel(number: number): string {
  return `v${number}`;
}

/** "Agent" for the Architect's versions, "You" for edits and restores. */
export function sourceLabel(source: "agent" | "user"): string {
  return source === "agent" ? "Agent" : "You";
}

/** The older versions Compare can start from, newest first (all but the newest). */
export function olderVersionNumbers(latestNumber: number): readonly number[] {
  return Array.from({ length: Math.max(0, latestNumber - 1) }, (_, index) => latestNumber - 1 - index);
}

/** The version number the menu marks as current, or null while comparing. */
export function shownNumber(view: SpecView, latestNumber: number): number | null {
  if (view.mode === "version") return view.number;
  return view.mode === "edit" ? latestNumber : null;
}
