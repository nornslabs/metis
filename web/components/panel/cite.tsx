"use client";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { useSourceIndex, useSourceNav } from "@/lib/research/source-context";

const MARK_CLASS =
  "inline-grid h-3.75 min-w-3.75 place-items-center border bg-background px-0.75 font-mono text-micro leading-none font-medium text-muted-foreground";

/** The number in its bordered square, without a click action (the Sources rows). */
export function CiteMark({ number, className }: { number: number; className?: string }) {
  return (
    <span aria-hidden="true" className={cn(MARK_CLASS, className)}>
      {number}
    </span>
  );
}

/**
 * A numbered source chip after a claim. The tooltip shows the domain; a click opens the Research
 * pane on that source. It renders nothing for a URL that has no source number, so every chip works.
 */
export function Cite({ url }: { url: string | null | undefined }) {
  const index = useSourceIndex();
  const { openSource } = useSourceNav();
  const entry = index.entryFor(url);
  if (!entry) return null;
  const { number } = entry;
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            data-testid="cite"
            data-source={number}
            aria-label={`Source ${number}: ${entry.domain}`}
            onClick={() => openSource(number)}
            className={cn(
              MARK_CLASS,
              "relative -top-px mx-px cursor-pointer transition-colors hover:border-ring hover:text-foreground focus-visible:border-ring focus-visible:text-foreground focus-visible:outline-none",
            )}
          />
        }
      >
        {number}
      </TooltipTrigger>
      <TooltipContent>{entry.domain}</TooltipContent>
    </Tooltip>
  );
}
