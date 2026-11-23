"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import { owlFrames, type OwlFrames } from "@/lib/chat/ascii-owl-frames";
import { useReducedMotion } from "@/lib/use-reduced-motion";

/** While working, the eyes shut for this long ... */
const BLINK_MS = 160;
/** ... every this often (the same beat as `OwlMark`). */
const BLINK_EVERY_MS = 2600;

/** True for `BLINK_MS` every `BLINK_EVERY_MS` while `active`; never under reduced motion. */
function useBlink(active: boolean): boolean {
  const reduced = useReducedMotion();
  const [shut, setShut] = useState(false);
  useEffect(() => {
    if (!active || reduced) return;
    let reopenTimer: ReturnType<typeof setTimeout> | undefined;
    const blinkTimer = setInterval(() => {
      setShut(true);
      reopenTimer = setTimeout(() => setShut(false), BLINK_MS);
    }, BLINK_EVERY_MS);
    return () => {
      clearInterval(blinkTimer);
      clearTimeout(reopenTimer);
      setShut(false);
    };
  }, [active, reduced]);
  return shut;
}

const noSubscription = (): (() => void) => () => undefined;

/** The frames, drawn on the client only: null on the server and the first render, so hydration matches. */
function useOwlFrames(): OwlFrames | null {
  return useSyncExternalStore(noSubscription, owlFrames, () => null);
}

/**
 * The faint ASCII owl behind the conversation (ui-context.md, AsciiOwl). Decoration only: hidden
 * from assistive technology, never catches the pointer, and fades in over 0.6s. While Metis is
 * `working` its eyes shut for a moment every 2.6s.
 */
export function AsciiOwl({ working }: { working: boolean }) {
  const frames = useOwlFrames();
  const shut = useBlink(working);
  if (!frames) return null;
  return (
    <div
      aria-hidden="true"
      data-testid="ascii-owl"
      className="pointer-events-none absolute inset-0 z-0 grid place-items-center overflow-hidden pb-35 select-none motion-safe:animate-in motion-safe:duration-600 motion-safe:fade-in"
    >
      <pre
        data-eyes={shut ? "shut" : "open"}
        className="m-0 font-mono text-ascii tracking-ascii whitespace-pre text-foreground opacity-7.5 max-guides:text-ascii-phone max-guides:tracking-ascii-phone dark:opacity-9"
      >
        {shut ? frames.shut : frames.open}
      </pre>
    </div>
  );
}
