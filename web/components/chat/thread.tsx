import type { ReactNode } from "react";

/** The conversation column; new steps and text are announced politely. */
export function Thread({ children }: { children: ReactNode }) {
  return (
    <div
      aria-live="polite"
      aria-label="Conversation"
      role="log"
      className="mx-auto flex w-(--col) flex-col gap-4 px-5 pt-4 pb-2 max-guides:px-4"
    >
      {children}
    </div>
  );
}
