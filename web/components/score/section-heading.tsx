import type { ReactNode } from "react";

/** The small uppercase label above a group in the score section (History, Suggestions, …). */
export function SectionHeading({ children }: { children: ReactNode }) {
  return <h3 className="text-meta font-medium text-muted-foreground uppercase tracking-label">{children}</h3>;
}
