"use client";

import { ExternalLink } from "lucide-react";
import { useEffect, useRef } from "react";

import { CiteMark } from "@/components/panel/cite";
import type { SourceEntry } from "@/lib/research/sources";
import { useSourceNav } from "@/lib/research/source-context";

const FLASH_MS = 1600;

/** `smooth` unless the user asked for less motion. */
function scrollBehavior(): ScrollBehavior {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
}

/**
 * A row of the Sources list. When a chip asks for this source the row scrolls to the middle,
 * takes focus on its link and flashes (the flash itself is CSS and is off under reduced motion).
 */
export function SourceRow({ entry }: { entry: SourceEntry }) {
  const { target, consumeTarget } = useSourceNav();
  const rowRef = useRef<HTMLLIElement>(null);
  const linkRef = useRef<HTMLAnchorElement>(null);
  const flashTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const requested = target?.number === entry.number ? target : null;

  useEffect(() => {
    const row = rowRef.current;
    if (!requested || !row) return;
    row.scrollIntoView({ block: "center", behavior: scrollBehavior() });
    linkRef.current?.focus({ preventScroll: true });
    // The flash is a DOM attribute the CSS animates; removing it and forcing a reflow restarts it.
    delete row.dataset.flash;
    void row.offsetWidth;
    row.dataset.flash = "true";
    clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => delete row.dataset.flash, FLASH_MS);
    // Consuming clears `requested`, which re-runs this effect: the timer must outlive that run.
    consumeTarget(requested);
  }, [requested, consumeTarget]);

  useEffect(() => () => clearTimeout(flashTimer.current), []);

  return (
    <li
      ref={rowRef}
      id={`src-${entry.number}`}
      data-testid="source-row"
      className="grid grid-cols-[auto_1fr_auto] items-start gap-2.5 border-b px-1 py-1.75 last:border-b-0 data-flash:animate-src-flash motion-reduce:animate-none"
    >
      <CiteMark number={entry.number} className="mt-0.5" />
      <span className="flex min-w-0 flex-col gap-px">
        <b className="truncate text-control font-medium">{entry.title}</b>
        <small className="text-meta text-muted-foreground">{entry.domain}</small>
      </span>
      <a
        ref={linkRef}
        href={entry.href}
        target="_blank"
        rel="noopener noreferrer nofollow"
        aria-label={`Open ${entry.domain}`}
        className="grid size-5 place-items-center text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
      >
        <ExternalLink size={13} aria-hidden="true" />
        <span className="sr-only">(opens in a new tab)</span>
      </a>
    </li>
  );
}
