"use client";

import { useSearchParams } from "next/navigation";
import {
  createContext,
  Suspense,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";

import { hasOpenOverlay, isTypingTarget } from "./dom-guards";
import { useOutputAvailability } from "./output-availability";
import {
  CLOSED_PANELS,
  closePanel,
  openPanel,
  topMostPanel,
  type PanelName,
  type PanelState,
} from "./panel-state";
import { PANEL_PARAM, parseOutputPane, withOutputPane, type OutputPane } from "./panes";

const FALLBACK_PANE: OutputPane = "score";
const HISTORY_SHORTCUT = "/";

export interface WorkspacePanels {
  historyOpen: boolean;
  openHistory: () => void;
  closeHistory: () => void;
  /** The pane the open output panel shows, or null while it is closed. */
  pane: OutputPane | null;
  outputOpen: boolean;
  /** Opens the output panel on `pane`, or on the last pane used (else the first with content). */
  openOutput: (pane?: OutputPane) => void;
  closeOutput: () => void;
  /** The history panel's search box, which `/` focuses. */
  searchRef: RefObject<HTMLInputElement | null>;
  /** The toggles, so focus can return to the one whose panel just closed. */
  toggleRefs: Record<PanelName, RefObject<HTMLButtonElement | null>>;
}

const WorkspacePanelsContext = createContext<WorkspacePanels | null>(null);

export function useWorkspacePanels(): WorkspacePanels {
  const value = useContext(WorkspacePanelsContext);
  if (!value) throw new Error("useWorkspacePanels must be used inside <WorkspacePanelsProvider>");
  return value;
}

/** Writes `?panel=` without a navigation; Next's router picks the change up for `useSearchParams`. */
function writePaneToUrl(pane: OutputPane | null) {
  const url = withOutputPane(window.location.pathname, new URLSearchParams(window.location.search), pane);
  window.history.replaceState(null, "", url);
}

/** True when focus is on the page body or inside `panel`, i.e. closing it would strand focus. */
function focusWouldBeLost(panel: PanelName): boolean {
  const active = document.activeElement;
  if (!active || active === document.body) return true;
  return document.querySelector(`[data-frame="${panel}"]`)?.contains(active) ?? false;
}

/** Reports `?panel=` to the provider, so back/forward and typed links open the output panel. */
function PanelUrlSync({ onChange }: { onChange: (pane: OutputPane | null) => void }) {
  const pane = parseOutputPane(useSearchParams().get(PANEL_PARAM));
  useEffect(() => onChange(pane), [pane, onChange]);
  return null;
}

/**
 * State of the history panel (local) and the output panel (`?panel=`), plus the Esc and `/` keys.
 * `?panel=` is read behind its own Suspense boundary so pages still prerender.
 */
export function WorkspacePanelsProvider({ children }: { children: ReactNode }) {
  const [panels, setPanels] = useState<PanelState>(CLOSED_PANELS);
  const [pane, setPane] = useState<OutputPane | null>(null);
  const panesWithContent = useOutputAvailability().panes;

  const panelsRef = useRef(panels);
  const paneRef = useRef(pane);
  const lastPaneRef = useRef<OutputPane | null>(null);
  const restoreFocusTo = useRef<PanelName | null>(null);
  const historyToggle = useRef<HTMLButtonElement>(null);
  const outputToggle = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const focusSearchWhenOpen = useRef(false);
  const toggleRefs = useMemo(() => ({ history: historyToggle, output: outputToggle }), []);

  const commit = useCallback((nextPanels: PanelState, nextPane: OutputPane | null) => {
    panelsRef.current = nextPanels;
    paneRef.current = nextPane;
    if (nextPane !== null) lastPaneRef.current = nextPane;
    setPanels(nextPanels);
    setPane(nextPane);
  }, []);

  const showPane = useCallback(
    (next: OutputPane) => {
      const opened = openPanel(panelsRef.current, "output", window.innerWidth);
      commit(opened, next);
    },
    [commit],
  );

  const hideOutput = useCallback(() => {
    commit(closePanel(panelsRef.current, "output"), null);
  }, [commit]);

  const openOutput = useCallback(
    (requested?: OutputPane) => {
      const next = requested ?? paneRef.current ?? lastPaneRef.current ?? panesWithContent[0] ?? FALLBACK_PANE;
      showPane(next);
      writePaneToUrl(next);
    },
    [panesWithContent, showPane],
  );

  const closeOutput = useCallback(() => {
    if (focusWouldBeLost("output")) restoreFocusTo.current = "output";
    hideOutput();
    writePaneToUrl(null);
  }, [hideOutput]);

  const openHistory = useCallback(() => {
    const opened = openPanel(panelsRef.current, "history", window.innerWidth);
    const closesOutput = panelsRef.current.outputOpen && !opened.outputOpen;
    commit(opened, closesOutput ? null : paneRef.current);
    if (closesOutput) writePaneToUrl(null);
  }, [commit]);

  const closeHistory = useCallback(() => {
    if (focusWouldBeLost("history")) restoreFocusTo.current = "history";
    commit(closePanel(panelsRef.current, "history"), paneRef.current);
  }, [commit]);

  // The URL is the source of truth for the output panel: follow it when it changes under us.
  const followUrl = useCallback(
    (fromUrl: OutputPane | null) => {
      if (fromUrl === paneRef.current) return;
      if (fromUrl === null) hideOutput();
      else showPane(fromUrl);
    },
    [hideOutput, showPane],
  );

  // After a panel closes, its toggle comes back: give it the focus the panel held.
  useEffect(() => {
    const closed = restoreFocusTo.current;
    if (closed === null) return;
    const stillOpen = closed === "history" ? panels.historyOpen : panels.outputOpen;
    if (stillOpen) return;
    restoreFocusTo.current = null;
    toggleRefs[closed].current?.focus();
  }, [panels, toggleRefs]);

  // `/` while history was closed: focus the search box once the panel is open (it is inert before).
  useEffect(() => {
    if (!panels.historyOpen || !focusSearchWhenOpen.current) return;
    focusSearchWhenOpen.current = false;
    searchRef.current?.focus();
  }, [panels.historyOpen]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.defaultPrevented || isTypingTarget(event.target) || hasOpenOverlay()) return;
      if (event.key === "Escape") {
        const top = topMostPanel(panelsRef.current);
        if (top === "history") closeHistory();
        else if (top === "output") closeOutput();
        else return;
        event.preventDefault();
        return;
      }
      const plain = !event.metaKey && !event.ctrlKey && !event.altKey;
      if (event.key === HISTORY_SHORTCUT && plain) {
        event.preventDefault();
        if (panelsRef.current.historyOpen) searchRef.current?.focus();
        else {
          focusSearchWhenOpen.current = true;
          openHistory();
        }
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [closeHistory, closeOutput, openHistory]);

  const value = useMemo<WorkspacePanels>(
    () => ({
      historyOpen: panels.historyOpen,
      openHistory,
      closeHistory,
      pane,
      outputOpen: panels.outputOpen,
      openOutput,
      closeOutput,
      searchRef,
      toggleRefs,
    }),
    [panels, pane, openHistory, closeHistory, openOutput, closeOutput, searchRef, toggleRefs],
  );

  return (
    <WorkspacePanelsContext value={value}>
      <Suspense fallback={null}>
        <PanelUrlSync onChange={followUrl} />
      </Suspense>
      {children}
    </WorkspacePanelsContext>
  );
}
