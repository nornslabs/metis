"use client";

import { X } from "lucide-react";
import { useRef, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useOutputAvailability } from "@/lib/workspace/output-availability";
import { OUTPUT_PANES, type OutputPane } from "@/lib/workspace/panes";
import { useFocusOnOverlayOpen } from "@/lib/workspace/use-focus-on-open";
import { useWorkspacePanels } from "@/lib/workspace/workspace-panels";
import { cn } from "@/lib/utils";

const PANE_LABEL: Record<OutputPane, string> = {
  score: "Score",
  research: "Research",
  suggestions: "Suggestions",
  spec: "Spec",
  plan: "Plan",
};

/**
 * The right panel's shell: a tab strip with a close button and a body slot, `clamp(360px, 36vw,
 * 500px)` wide, pushing the chat pane (a full-screen overlay under 820px). The panes' content
 * is filled by SHIP-290 and later; a pane without content has a disabled tab.
 */
export function OutputPanel({ children }: { children?: ReactNode }) {
  const { outputOpen, pane, openOutput, closeOutput } = useWorkspacePanels();
  const { panes: withContent } = useOutputAvailability();
  const closeRef = useRef<HTMLButtonElement>(null);
  useFocusOnOverlayOpen(outputOpen, closeRef);

  return (
    <aside
      id="output-panel"
      aria-label="Output"
      data-frame="output"
      data-open={outputOpen}
      inert={!outputOpen}
      className={cn(
        "relative z-10 w-0 shrink-0 overflow-hidden bg-background transition-[width] duration-250 ease-panel motion-reduce:transition-none",
        "data-[open=true]:w-(--panel-w)",
        // Under 820px: a full-screen overlay from the right that slides instead of growing.
        "max-guides:fixed max-guides:inset-y-0 max-guides:right-0 max-guides:z-46 max-guides:w-full max-guides:translate-x-full",
        "max-guides:transition-transform max-guides:data-[open=true]:w-full max-guides:data-[open=true]:translate-x-0",
      )}
    >
      <div className="flex h-full w-(--panel-w) flex-col border-x max-guides:w-full max-guides:border-x-0">
        <div className="flex h-9.5 shrink-0 items-stretch justify-between border-b">
          <div role="tablist" aria-label="Output panes" className="flex overflow-x-auto">
            {OUTPUT_PANES.map((name) => {
              const selected = pane === name;
              return (
                <button
                  key={name}
                  type="button"
                  role="tab"
                  id={`output-tab-${name}`}
                  aria-selected={selected}
                  aria-controls="output-body"
                  disabled={!withContent.includes(name)}
                  onClick={() => openOutput(name)}
                  className={cn(
                    "relative flex items-center gap-1.5 border-r px-3 text-note whitespace-nowrap text-muted-foreground",
                    "enabled:hover:bg-accent enabled:hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50",
                    selected && "bg-background text-foreground before:absolute before:inset-x-0 before:top-0 before:h-0.5 before:bg-foreground",
                  )}
                >
                  {PANE_LABEL[name]}
                </button>
              );
            })}
          </div>
          <Button
            ref={closeRef}
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Close output"
            className="m-1.5 shrink-0"
            onClick={closeOutput}
          >
            <X size={14} strokeWidth={2} />
          </Button>
        </div>
        <div
          id="output-body"
          role="tabpanel"
          aria-labelledby={pane ? `output-tab-${pane}` : undefined}
          className="min-h-0 flex-1 overflow-y-auto"
        >
          {children ?? <p className="p-4 text-note text-muted-foreground">Nothing to show here yet.</p>}
        </div>
      </div>
    </aside>
  );
}
