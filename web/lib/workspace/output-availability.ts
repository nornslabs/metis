import { createContext, useContext } from "react";

import type { OutputPane } from "./panes";

export interface OutputAvailability {
  /** Panes that have content; the others are disabled tabs. */
  panes: readonly OutputPane[];
  /** Panes whose output (or a newer version of it) the user has not seen yet. */
  unseenPanes: readonly OutputPane[];
  /** True while any output is unseen: the right toggle shows its dot. */
  unseen: boolean;
}

/** No pane has content until a page registers some by providing this context. */
export const NO_OUTPUT: OutputAvailability = { panes: [], unseenPanes: [], unseen: false };

export const OutputAvailabilityContext = createContext<OutputAvailability>(NO_OUTPUT);

export function useOutputAvailability(): OutputAvailability {
  return useContext(OutputAvailabilityContext);
}
