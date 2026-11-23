"use client";

import type { ReactNode } from "react";

import { EdgeToggle } from "@/components/chat/edge-toggle";
import { HistoryPanel } from "@/components/history/history-panel";
import { OutputPanel } from "@/components/panel/output-panel";
import { SourceNavProvider } from "@/lib/research/source-context";
import { OutputRegistryProvider } from "@/lib/workspace/output-registry";
import { RunActivityProvider } from "@/lib/workspace/run-activity";
import { useNarrow } from "@/lib/workspace/use-narrow";
import { WorkspacePanelsProvider, useWorkspacePanels } from "@/lib/workspace/workspace-panels";

/** Dims the page behind the history overlay (under 820px); a tap closes it. */
function HistoryScrim() {
  const { historyOpen, closeHistory } = useWorkspacePanels();
  return (
    <button
      type="button"
      tabIndex={-1}
      aria-hidden="true"
      data-testid="history-scrim"
      onClick={closeHistory}
      className="fixed inset-0 z-45 hidden bg-black/40 data-[open=true]:max-guides:block"
      data-open={historyOpen}
    />
  );
}

function WorkspaceRow({ children }: { children: ReactNode }) {
  const { historyOpen, outputOpen } = useWorkspacePanels();
  const narrow = useNarrow();
  // An overlay is modal: the chat pane behind it is out of reach until it closes.
  const covered = narrow && (historyOpen || outputOpen);

  return (
    <div className="relative z-1 mx-auto flex min-h-0 w-(--frame) flex-1 max-compact:w-full">
      <HistoryPanel />
      <HistoryScrim />
      <div inert={covered} className="@container/chat relative flex min-h-0 min-w-0 flex-1 flex-col">
        {/* Zero-height probe: the chat column. Its edges are the guide lines; the toggles sit on them. */}
        <div data-frame="column" className="chat-col relative z-20 h-0 shrink-0">
          <EdgeToggle side="left" />
          <EdgeToggle side="right" />
        </div>
        {children}
      </div>
      <OutputPanel />
    </div>
  );
}

/** `[history panel | chat pane | output panel]` inside the frame (ui-context.md, Layout). */
export function WorkspaceLayout({ children }: { children: ReactNode }) {
  return (
    <OutputRegistryProvider>
      <RunActivityProvider>
        <WorkspacePanelsProvider>
          <SourceNavProvider>
            <WorkspaceRow>{children}</WorkspaceRow>
          </SourceNavProvider>
        </WorkspacePanelsProvider>
      </RunActivityProvider>
    </OutputRegistryProvider>
  );
}
