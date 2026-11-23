"use client";

import { useSyncExternalStore } from "react";

/** The `guides` breakpoint: under it the side panels are overlays. Mirrors `app/globals.css`. */
const NARROW_QUERY = "(max-width: 819.98px)";

function subscribe(onChange: () => void): () => void {
  const query = window.matchMedia(NARROW_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** True under 820px. False on the server and the first render, so hydration matches. */
export function useNarrow(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(NARROW_QUERY).matches,
    () => false,
  );
}
