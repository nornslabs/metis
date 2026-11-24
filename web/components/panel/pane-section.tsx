import type { ReactNode } from "react";

interface PaneSectionProps {
  heading: string;
  /** Right-aligned note on the heading row ("weight · score"). */
  aside?: string;
  children: ReactNode;
}

/** A block of a pane body: 14/16px padding, an uppercase label, a bottom line. */
export function PaneSection({ heading, aside, children }: PaneSectionProps) {
  return (
    <section aria-label={heading} className="flex flex-col gap-2 border-b px-4 py-3.5 last:border-b-0">
      <h3 className="flex items-center justify-between gap-2 text-meta font-medium text-muted-foreground uppercase tracking-label">
        <span>{heading}</span>
        {aside ? <span className="font-normal normal-case tracking-normal">{aside}</span> : null}
      </h3>
      {children}
    </section>
  );
}
