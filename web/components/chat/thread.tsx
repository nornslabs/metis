import type { ReactNode } from "react";

/**
 * The conversation column, anchored to the bottom: messages stack upward and any free space is
 * above them. New steps and text are announced politely.
 */
export function Thread({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-full flex-col justify-end">
      <div
        aria-live="polite"
        aria-label="Conversation"
        role="log"
        className="chat-col flex flex-col gap-4 px-5 pt-4 pb-2 max-guides:px-4"
      >
        {children}
      </div>
    </div>
  );
}
