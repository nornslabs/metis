import type { ReactNode } from "react";

interface PaneFooterProps {
  /** The pane's actions, left. */
  children?: ReactNode;
  /** A muted line, right ("Updated today"). */
  meta?: ReactNode;
}

/** The footer a pane registers: actions on the left, a muted meta line on the right. */
export function PaneFooter({ children, meta }: PaneFooterProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5 px-4 py-2.5">
      {children ? <div className="flex flex-wrap items-start gap-1.5">{children}</div> : <span />}
      {meta ? <span className="pt-1.5 text-meta text-muted-foreground">{meta}</span> : null}
    </div>
  );
}
