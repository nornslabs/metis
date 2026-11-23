import { describe, expect, test } from "vitest";

import { CLOSED_PANELS, closePanel, openPanel, topMostPanel, type PanelState } from "./panel-state";

const LAPTOP = 1440;
const SMALL_LAPTOP = 1100;

describe("openPanel", () => {
  test("keeps both panels open from 1200px up", () => {
    const state = openPanel(openPanel(CLOSED_PANELS, "history", LAPTOP), "output", LAPTOP);

    expect(state).toEqual({ historyOpen: true, outputOpen: true, lastOpened: "output" });
  });

  test("closes the other panel under 1200px", () => {
    const history = openPanel(CLOSED_PANELS, "history", SMALL_LAPTOP);

    const output = openPanel(history, "output", SMALL_LAPTOP);
    const back = openPanel(output, "history", SMALL_LAPTOP);

    expect(output).toEqual({ historyOpen: false, outputOpen: true, lastOpened: "output" });
    expect(back).toEqual({ historyOpen: true, outputOpen: false, lastOpened: "history" });
  });

  test("treats exactly 1200px as wide enough for both", () => {
    const state = openPanel(openPanel(CLOSED_PANELS, "history", 1200), "output", 1200);

    expect(state.historyOpen && state.outputOpen).toBe(true);
  });
});

describe("closePanel", () => {
  test("makes the remaining open panel the next one Esc closes", () => {
    const both = openPanel(openPanel(CLOSED_PANELS, "history", LAPTOP), "output", LAPTOP);

    const state = closePanel(both, "output");

    expect(state).toEqual({ historyOpen: true, outputOpen: false, lastOpened: "history" });
  });

  test("leaves nothing open and no last panel", () => {
    const state = closePanel(openPanel(CLOSED_PANELS, "history", LAPTOP), "history");

    expect(state).toEqual(CLOSED_PANELS);
  });
});

describe("topMostPanel", () => {
  test("is the panel opened last", () => {
    const state: PanelState = { historyOpen: true, outputOpen: true, lastOpened: "history" };

    expect(topMostPanel(state)).toBe("history");
  });

  test("falls back to the open panel when the last one is closed", () => {
    expect(topMostPanel({ historyOpen: false, outputOpen: true, lastOpened: "history" })).toBe("output");
  });

  test("is null when nothing is open", () => {
    expect(topMostPanel(CLOSED_PANELS)).toBeNull();
  });
});
