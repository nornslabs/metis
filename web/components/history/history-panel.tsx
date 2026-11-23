"use client";

import { PanelLeftClose } from "lucide-react";
import { useRef, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useFocusOnOverlayOpen } from "@/lib/workspace/use-focus-on-open";
import { useWorkspacePanels } from "@/lib/workspace/workspace-panels";
import { cn } from "@/lib/utils";

/**
 * The left panel's shell: a 264px column that pushes the chat pane (an overlay under 820px). The
 * head has the title and a collapse button; `children` is the body, filled by SHIP-289.
 */
export function HistoryPanel({ children }: { children?: ReactNode }) {
  const { historyOpen, closeHistory } = useWorkspacePanels();
  const closeRef = useRef<HTMLButtonElement>(null);
  useFocusOnOverlayOpen(historyOpen, closeRef);

  return (
    <aside
      id="history-panel"
      aria-label="Ideas"
      data-frame="history"
      data-open={historyOpen}
      inert={!historyOpen}
      className={cn(
        "relative z-10 w-0 shrink-0 overflow-hidden bg-background transition-[width] duration-250 ease-panel motion-reduce:transition-none",
        "data-[open=true]:w-(--hist-w)",
        // Under 820px: an overlay from the left that slides instead of growing.
        "max-guides:fixed max-guides:inset-y-0 max-guides:left-0 max-guides:z-46 max-guides:w-(--overlay-w) max-guides:-translate-x-full",
        "max-guides:transition-transform max-guides:data-[open=true]:w-(--overlay-w) max-guides:data-[open=true]:translate-x-0",
      )}
    >
      <div className="flex h-full w-(--hist-w) flex-col border-x max-guides:w-full max-guides:border-l-0">
        <div className="flex h-9.5 shrink-0 items-center gap-1.5 border-b pr-2 pl-3">
          <h2 className="flex-1 text-meta font-medium tracking-label text-muted-foreground uppercase">Your ideas</h2>
          <Button
            ref={closeRef}
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Close history"
            onClick={closeHistory}
          >
            <PanelLeftClose size={14} strokeWidth={2} />
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </aside>
  );
}
