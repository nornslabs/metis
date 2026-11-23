import type { ReactNode } from "react";

import type { DockMode } from "@/lib/chat/dock-mode";

const ANNOUNCEMENT: Readonly<Record<DockMode, string>> = {
  busy: "Metis is working.",
  choice: "Metis has a question. Pick an answer.",
  text: "",
};

interface DockProps {
  mode: DockMode;
  /** The active mode's content: a `WorkingBar`, a `ChoicePicker` or a `Composer`. */
  children: ReactNode;
}

/**
 * The band at the bottom of the chat, one mode at a time. Its top edge is the input band line the
 * frame draws (`data-frame="band"`), so the line follows whichever mode shows.
 */
export function Dock({ mode, children }: DockProps) {
  return (
    <div data-frame="band" data-dock-mode={mode} className="relative shrink-0">
      {children}
      <p role="status" className="sr-only">
        {ANNOUNCEMENT[mode]}
      </p>
    </div>
  );
}
