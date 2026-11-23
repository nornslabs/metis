import type { ReactNode } from "react";

import { OwlMark, type OwlState } from "@/components/brand/owl-mark";

interface AgentMessageProps {
  /** Shown beside the "Metis" label, e.g. the idea's stage. */
  aside?: ReactNode;
  /** Only the latest agent message animates: `working` while busy, `waiting` while the dock asks. */
  owl?: OwlState;
  children: ReactNode;
}

/** Metis's reply: a 22px bordered owl and plain text, no bubble (ui-context.md, AgentMessage). */
export function AgentMessage({ aside, owl = "idle", children }: AgentMessageProps) {
  return (
    <div className="flex gap-2.5 motion-safe:animate-in motion-safe:duration-250 motion-safe:fade-in motion-safe:slide-in-from-bottom-1.5">
      <div aria-hidden="true" className="grid size-5.5 shrink-0 place-items-center border">
        <OwlMark state={owl} className="size-4" />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex h-5.5 items-center gap-2 text-meta font-medium text-muted-foreground">
          Metis
          {aside}
        </div>
        {children}
      </div>
    </div>
  );
}
