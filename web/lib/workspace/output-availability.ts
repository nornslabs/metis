import { createContext, useContext } from "react";

import type { OutputPane } from "./panes";

export interface OutputAvailability {
  /** Panes that have content; the others are disabled tabs. */
  panes: readonly OutputPane[];
  /** True while an output exists that the user has not opened yet. */
  unseen: boolean;
}

/** No pane has content until SHIP-290 and later register theirs by providing this context. */
export const NO_OUTPUT: OutputAvailability = { panes: [], unseen: false };

export const OutputAvailabilityContext = createContext<OutputAvailability>(NO_OUTPUT);

export function useOutputAvailability(): OutputAvailability {
  return useContext(OutputAvailabilityContext);
}
