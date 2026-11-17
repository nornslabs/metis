import { Layers } from "lucide-react";
import type { ReactNode } from "react";

interface AgentMessageProps {
  /** Shown beside the "Metis" label, e.g. the idea's stage. */
  aside?: ReactNode;
  children: ReactNode;
}

/** Metis's reply: a 22px mark and plain text, no bubble (ui-context.md, AgentMessage). */
export function AgentMessage({ aside, children }: AgentMessageProps) {
  return (
    <div className="flex gap-2.5 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1.5">
      <div aria-hidden="true" className="grid size-5.5 shrink-0 place-items-center border">
        <Layers size={12} strokeWidth={2} />
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
