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

type PaneContent = Readonly<Partial<Record<OutputPane, ReactNode>>>;

interface OutputRegistryActions {
  /**
   * Gives `pane` its content; the pane's tab and the right toggle turn on. `scope` (the idea id)
   * tells a new output from new content for one already announced: only a new output is unseen.
   */
  register: (pane: OutputPane, content: ReactNode, scope: string) => void;
  /** Takes the pane away (the idea page left, or its output is gone). */
  unregister: (pane: OutputPane) => void;
  /** Called once the output panel is open: nothing is unseen any more. */
  markSeen: () => void;
}

const ActionsContext = createContext<OutputRegistryActions | null>(null);
const ContentContext = createContext<PaneContent>({});

/**
 * Which panes have content, the content itself, and whether something new is unseen. The idea page
 * registers what it produced; the output panel and the edge toggle read it. Actions and content
 * are separate contexts so a page that only registers is not re-rendered by a content change.
 */
export function OutputRegistryProvider({ children }: { children: ReactNode }) {
  const [content, setContent] = useState<PaneContent>({});
  const [unseen, setUnseen] = useState(false);
  const announced = useRef(new Set<string>());

  const register = useCallback((pane: OutputPane, next: ReactNode, scope: string) => {
    setContent((current) => ({ ...current, [pane]: next }));
    const key = `${scope}:${pane}`;
    if (announced.current.has(key)) return;
    announced.current.add(key);
    setUnseen(true);
  }, []);

  const unregister = useCallback((pane: OutputPane) => {
    setContent((current) => {
      if (!(pane in current)) return current;
      return Object.fromEntries(Object.entries(current).filter(([name]) => name !== pane)) as PaneContent;
    });
  }, []);

  const markSeen = useCallback(() => setUnseen(false), []);

  const actions = useMemo(() => ({ register, unregister, markSeen }), [register, unregister, markSeen]);
  const availability = useMemo<OutputAvailability>(
    () => ({ panes: OUTPUT_PANES.filter((pane) => pane in content), unseen }),
    [content, unseen],
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

/** The content registered for `pane`, or undefined. */
export function useOutputContent(pane: OutputPane | null): ReactNode {
  const content = useContext(ContentContext);
  return pane === null ? undefined : content[pane];
}

/**
 * Registers `content` for `pane` while `content` is given; unregisters when it becomes null or on
 * unmount. `scope` is what the output belongs to (the idea id).
 */
export function useRegisterOutput(pane: OutputPane, content: ReactNode | null, scope: string): void {
  const { register, unregister } = useActions();
  useEffect(() => {
    if (content === null) {
      unregister(pane);
      return;
    }
    register(pane, content, scope);
    return () => unregister(pane);
  }, [pane, content, scope, register, unregister]);
}

/** Clears the unseen mark while the panel is open, also for an output that arrives after it opened. */
export function useMarkOutputSeen(open: boolean): void {
  const { markSeen } = useActions();
  const { unseen } = useOutputAvailability();
  useEffect(() => {
    if (open && unseen) markSeen();
  }, [open, unseen, markSeen]);
}
