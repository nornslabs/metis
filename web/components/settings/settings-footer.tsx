import type { ReactNode } from "react";

/** The sheet's sticky footer: actions on the right, a line above. */
export function SettingsFooter({ children }: { children: ReactNode }) {
  return <div className="flex shrink-0 justify-end gap-2 border-t px-4 py-2">{children}</div>;
}
