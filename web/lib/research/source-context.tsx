"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { buildSourceIndex, type SourceIndex } from "@/lib/research/sources";
import { useWorkspacePanels } from "@/lib/workspace/workspace-panels";

const EMPTY_INDEX: SourceIndex = buildSourceIndex(null);

const SourceIndexContext = createContext<SourceIndex>(EMPTY_INDEX);

/** The numbered sources of the idea on the page. Wrapped around each pane body that cites a source. */
export function SourceIndexProvider({ index, children }: { index: SourceIndex; children: ReactNode }) {
  return <SourceIndexContext value={index}>{children}</SourceIndexContext>;
}

export function useSourceIndex(): SourceIndex {
  return useContext(SourceIndexContext);
}

/** A request to land on a source row. `nonce` makes a second click on the same chip a new request. */
export interface SourceTarget {
  readonly number: number;
  readonly nonce: number;
}

interface SourceNav {
  target: SourceTarget | null;
  /** Opens the Research pane (if needed) and asks its row for `number` to scroll into view and flash. */
  openSource: (number: number) => void;
  /** The row that handled the request calls this, so a later visit to the pane does not replay it. */
  consumeTarget: (target: SourceTarget) => void;
}

const SourceNavContext = createContext<SourceNav | null>(null);

/** Must sit inside `WorkspacePanelsProvider`: opening a source opens the output panel on Research. */
export function SourceNavProvider({ children }: { children: ReactNode }) {
  const { openOutput } = useWorkspacePanels();
  const [target, setTarget] = useState<SourceTarget | null>(null);

  const openSource = useCallback(
    (number: number) => {
      setTarget((current) => ({ number, nonce: (current?.nonce ?? 0) + 1 }));
      openOutput("research");
    },
    [openOutput],
  );
  const consumeTarget = useCallback((handled: SourceTarget) => {
    setTarget((current) => (current?.nonce === handled.nonce ? null : current));
  }, []);

  const value = useMemo(() => ({ target, openSource, consumeTarget }), [target, openSource, consumeTarget]);
  return <SourceNavContext value={value}>{children}</SourceNavContext>;
}

const NO_NAV: SourceNav = { target: null, openSource: () => undefined, consumeTarget: () => undefined };

export function useSourceNav(): SourceNav {
  return useContext(SourceNavContext) ?? NO_NAV;
}
