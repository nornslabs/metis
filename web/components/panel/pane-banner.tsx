import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** An amber alert row at the top of a pane (a conflict, a failed save): text left, an action right. */
export function PaneBanner({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div role="alert" className={cn("flex flex-wrap items-center gap-2 border border-warning bg-card px-2.5 py-2 text-control", className)}>
      {children}
    </div>
  );
}
