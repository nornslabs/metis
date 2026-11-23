"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { OutputAvailabilityContext, useOutputAvailability, type OutputAvailability } from "./output-availability";
import { OUTPUT_PANES, type OutputPane } from "./panes";

/** What a pane puts in the output panel. */
export interface PaneOutput {
  /** The scrolling body. */
  readonly body: ReactNode;
  /** The sticky footer: the pane's actions. */
  readonly footer?: ReactNode;
  /** The tab's count (a number, or "v2" for the spec). */
  readonly count?: string;
  /**
   * Changes when the output is new or a new version of it. A new value lights the unseen mark
   * (the right toggle's dot, the tab's dot); edits that keep it the same do not.
   */
  readonly version: string;
}

type PaneContent = Readonly<Partial<Record<OutputPane, PaneOutput>>>;

interface OutputRegistryActions {
  /** Gives `pane` its output; its tab and the right toggle turn on. `scope` is the idea id. */
  register: (pane: OutputPane, output: PaneOutput, scope: string) => void;
  /** Takes the pane's content away; the unseen mark stays, so a re-register (new memo) keeps the dot. */
  unregister: (pane: OutputPane) => void;
  /** The output is gone or its page left: forget it and its unseen mark. */
  release: (pane: OutputPane, scope: string) => void;
  /** Called while `pane` is shown in the open panel: nothing there is unseen any more. */
  markSeen: (pane: OutputPane) => void;
}

const ActionsContext = createContext<OutputRegistryActions | null>(null);
const ContentContext = createContext<PaneContent>({});

/**
 * Which panes have output, the output itself, and which are unseen. The idea page registers what
 * it produced; the output panel and the edge toggle read it. Actions and content are separate
 * contexts so a page that only registers is not re-rendered by a content change.
 */
export function OutputRegistryProvider({ children }: { children: ReactNode }) {
  const [content, setContent] = useState<PaneContent>({});
  const [unseenPanes, setUnseenPanes] = useState<readonly OutputPane[]>([]);
  const announced = useRef(new Map<string, string>());

  const register = useCallback((pane: OutputPane, output: PaneOutput, scope: string) => {
    setContent((current) => ({ ...current, [pane]: output }));
    const key = `${scope}:${pane}`;
    if (announced.current.get(key) === output.version) return;
    announced.current.set(key, output.version);
    setUnseenPanes((current) => (current.includes(pane) ? current : [...current, pane]));
  }, []);

  const unregister = useCallback((pane: OutputPane) => {
    setContent((current) => {
      if (!(pane in current)) return current;
      return Object.fromEntries(Object.entries(current).filter(([name]) => name !== pane)) as PaneContent;
    });
  }, []);

  const release = useCallback((pane: OutputPane, scope: string) => {
    announced.current.delete(`${scope}:${pane}`);
    setUnseenPanes((current) => (current.includes(pane) ? current.filter((name) => name !== pane) : current));
  }, []);

  const markSeen = useCallback((pane: OutputPane) => {
    setUnseenPanes((current) => (current.includes(pane) ? current.filter((name) => name !== pane) : current));
  }, []);

  const actions = useMemo(() => ({ register, unregister, release, markSeen }), [register, unregister, release, markSeen]);
  const availability = useMemo<OutputAvailability>(
    () => ({
      panes: OUTPUT_PANES.filter((pane) => pane in content),
      unseenPanes,
      unseen: unseenPanes.length > 0,
    }),
    [content, unseenPanes],
  );

  return (
    <ActionsContext value={actions}>
      <ContentContext value={content}>
        <OutputAvailabilityContext value={availability}>{children}</OutputAvailabilityContext>
      </ContentContext>
    </ActionsContext>
  );
}

function useActions(): OutputRegistryActions {
  const actions = useContext(ActionsContext);
  if (!actions) throw new Error("Output registry hooks must be used inside <OutputRegistryProvider>");
  return actions;
}

/** The output registered for `pane`, or undefined. */
export function useOutputContent(pane: OutputPane | null): PaneOutput | undefined {
  const content = useContext(ContentContext);
  return pane === null ? undefined : content[pane];
}

/** Every registered pane's output (the tab strip reads the counts from it). */
export function useOutputPanes(): PaneContent {
  return useContext(ContentContext);
}

/**
 * Registers `output` for `pane` while `output` is given; unregisters when it becomes null or on
 * unmount. `scope` is what the output belongs to (the idea id). Memoize `output`.
 */
export function useRegisterOutput(pane: OutputPane, output: PaneOutput | null, scope: string): void {
  const { register, unregister, release } = useActions();
  useEffect(() => {
    if (output === null) {
      unregister(pane);
      release(pane, scope);
      return;
    }
    register(pane, output, scope);
    return () => unregister(pane);
  }, [pane, output, scope, register, unregister, release]);
  // Leaving the page (or the idea) forgets the output; a new version of it does not.
  useEffect(() => () => release(pane, scope), [pane, scope, release]);
}

/** Clears the unseen mark of the pane the open panel shows, also for a version that arrives while it is open. */
export function useMarkOutputSeen(open: boolean, pane: OutputPane | null): void {
  const { markSeen } = useActions();
  const { unseenPanes } = useOutputAvailability();
  const unseenHere = pane !== null && unseenPanes.includes(pane);
  useEffect(() => {
    if (open && pane !== null && unseenHere) markSeen(pane);
  }, [open, pane, unseenHere, markSeen]);
}
