"use client";

import { useEffect, useState } from "react";

import {
  computeFrameLines,
  sameFrameLines,
  type FrameLines,
  type FrameMeasure,
} from "@/lib/frame/lines";

/** `data-frame` values the frame measures; each is set once, by the component that owns the element. */
export type FramePart = "safe" | "column" | "header" | "footer" | "band";

/** How long measuring keeps running after a width transition starts (panels animate 250ms). */
const TRANSITION_MEASURE_MS = 400;

function rectOf(part: FramePart): DOMRect | null {
  return document.querySelector(`[data-frame="${part}"]`)?.getBoundingClientRect() ?? null;
}

function measureFrame(): FrameMeasure | null {
  const safe = rectOf("safe");
  const header = rectOf("header");
  const footer = rectOf("footer");
  if (!safe || !header || !footer) return null;
  const column = rectOf("column");
  const band = rectOf("band");
  return {
    viewportWidth: window.innerWidth,
    safe: { left: safe.left, right: safe.right },
    column: column ? { left: column.left, right: column.right } : null,
    headerBottom: header.bottom,
    footerTop: footer.top,
    bandTop: band ? band.top : null,
  };
}

/** Every element the frame measures. */
function framePartElements(): Set<Element> {
  return new Set(document.querySelectorAll("[data-frame]"));
}

function sameElements(a: ReadonlySet<Element>, b: ReadonlySet<Element>): boolean {
  return a.size === b.size && [...a].every((element) => b.has(element));
}

/**
 * Calls `onChange` (at most once per animation frame) whenever the frame may have moved: a measured
 * element resizes, the window resizes, a measured element mounts or unmounts (a page without a
 * composer has no input band), or a width transition runs. Returns the cleanup.
 */
function watchFrame(onChange: () => void): () => void {
  let frame = 0;
  let measureUntil = 0;
  let observed = framePartElements();

  const schedule = () => {
    if (frame === 0) frame = requestAnimationFrame(run);
  };
  const run = () => {
    frame = 0;
    onChange();
    if (performance.now() < measureUntil) schedule();
  };

  const resizeObserver = new ResizeObserver(schedule);
  observed.forEach((element) => resizeObserver.observe(element));

  const mutationObserver = new MutationObserver(() => {
    const current = framePartElements();
    if (sameElements(observed, current)) return;
    observed.forEach((element) => current.has(element) || resizeObserver.unobserve(element));
    current.forEach((element) => observed.has(element) || resizeObserver.observe(element));
    observed = current;
    schedule();
  });
  mutationObserver.observe(document.body, { childList: true, subtree: true });

  const onTransitionRun = (event: TransitionEvent) => {
    if (event.propertyName !== "width") return;
    measureUntil = performance.now() + TRANSITION_MEASURE_MS;
    schedule();
  };
  window.addEventListener("resize", schedule);
  document.addEventListener("transitionrun", onTransitionRun, true);
  document.addEventListener("transitionend", schedule, true);
  schedule();

  return () => {
    cancelAnimationFrame(frame);
    mutationObserver.disconnect();
    resizeObserver.disconnect();
    window.removeEventListener("resize", schedule);
    document.removeEventListener("transitionrun", onTransitionRun, true);
    document.removeEventListener("transitionend", schedule, true);
  };
}

/** Where the frame's lines are, in viewport px, or null until the first measure. */
export function useFrameLines(): FrameLines | null {
  const [lines, setLines] = useState<FrameLines | null>(null);

  useEffect(
    () =>
      watchFrame(() => {
        const measured = measureFrame();
        const next = measured ? computeFrameLines(measured) : null;
        setLines((previous) => (sameFrameLines(previous, next) ? previous : next));
      }),
    [],
  );

  return lines;
}
