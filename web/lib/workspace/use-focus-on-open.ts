"use client";

import { useEffect, type RefObject } from "react";

import { useNarrow } from "./use-narrow";

/** Moves focus to `target` when an overlay (a panel under 820px) opens; wider panels keep focus where it is. */
export function useFocusOnOverlayOpen(open: boolean, target: RefObject<HTMLElement | null>) {
  const narrow = useNarrow();
  useEffect(() => {
    if (open && narrow) target.current?.focus();
  }, [open, narrow, target]);
}
