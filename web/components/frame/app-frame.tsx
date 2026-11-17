import type { ReactNode } from "react";

import { AppFooter } from "./app-footer";
import { AppHeader } from "./app-header";
import { FrameBackground } from "./frame-background";
import { GridGuides } from "./grid-guides";

/** The framed app: rails and guides behind, header and footer on top, the page scrolling between. */
export function AppFrame({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex h-svh flex-col">
      <FrameBackground />
      <GridGuides />
      <AppHeader />
      <main className="relative z-10 flex min-h-0 flex-1 flex-col overflow-y-auto">
        {children}
      </main>
      <AppFooter />
    </div>
  );
}
