import { hasOptions } from "@/lib/chat/choice";
import type { RunInterrupt, RunStatus } from "@/lib/events/schemas";

/** Which part of the dock shows: typing, picking an answer, or watching Metis work. */
export type DockMode = "text" | "choice" | "busy";

export type DockModeInput = {
  readonly status: RunStatus;
  /** True when the live feed stopped before the run ended: the run is no longer followed. */
  readonly streamLost: boolean;
  /** The question the user can answer now, or null. */
  readonly question: RunInterrupt | null;
  /** True after "Something else": the composer takes the place of the options. */
  readonly typingOther: boolean;
  /** True once the user answered the pause the run is in: the run is about to move on. */
  readonly answered: boolean;
};

/**
 * One mode at a time, driven by the run: working (or just answered) → `busy`; a question with options → `choice`;
 * everything else (a new idea, a plain question, a finished run, a prompt above the composer) → `text`.
 */
export function dockMode({ status, streamLost, question, typingOther, answered }: DockModeInput): DockMode {
  if (streamLost) return "text";
  if (status === "awaiting_user" && answered) return "busy";
  if (status === "queued" || status === "running") return "busy";
  if (status === "awaiting_user" && question?.kind === "question" && hasOptions(question) && !typingOther) {
    return "choice";
  }
  return "text";
}
