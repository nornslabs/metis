export type PanelName = "history" | "output";

/** Under this viewport width (px) opening one side panel closes the other. */
export const SINGLE_PANEL_BELOW_PX = 1200;

export interface PanelState {
  historyOpen: boolean;
  outputOpen: boolean;
  /** The panel opened most recently; Esc closes it first. */
  lastOpened: PanelName | null;
}

export const CLOSED_PANELS: PanelState = { historyOpen: false, outputOpen: false, lastOpened: null };

/** Opens `panel`, closing the other one when the viewport is too narrow for both. */
export function openPanel(state: PanelState, panel: PanelName, viewportWidth: number): PanelState {
  const single = viewportWidth < SINGLE_PANEL_BELOW_PX;
  return {
    historyOpen: panel === "history" ? true : single ? false : state.historyOpen,
    outputOpen: panel === "output" ? true : single ? false : state.outputOpen,
    lastOpened: panel,
  };
}

/** Closes `panel`; the other panel, if open, becomes the one Esc closes next. */
export function closePanel(state: PanelState, panel: PanelName): PanelState {
  const next = {
    historyOpen: panel === "history" ? false : state.historyOpen,
    outputOpen: panel === "output" ? false : state.outputOpen,
  };
  const remaining: PanelName | null = next.historyOpen ? "history" : next.outputOpen ? "output" : null;
  return { ...next, lastOpened: remaining };
}

/** The panel Esc closes: the one opened last while open, else whichever is open, else none. */
export function topMostPanel(state: PanelState): PanelName | null {
  if (state.lastOpened === "history" && state.historyOpen) return "history";
  if (state.lastOpened === "output" && state.outputOpen) return "output";
  if (state.outputOpen) return "output";
  return state.historyOpen ? "history" : null;
}
