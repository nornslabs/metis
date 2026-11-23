import type { ReactNode } from "react";

import { ChoicePicker } from "@/components/chat/choice-picker";
import { Dock } from "@/components/chat/dock";
import { WorkingBar } from "@/components/chat/working-bar";
import type { DockMode } from "@/lib/chat/dock-mode";
import type { QuestionInterrupt, QuestionOption } from "@/lib/events/schemas";

type OfferedQuestion = QuestionInterrupt & { options: readonly QuestionOption[] };

interface RunDockProps {
  mode: DockMode;
  working: { label: string; counter: string | null; onStop: () => void; stopping: boolean };
  /** The question with options and what to do with a pick; used in `choice` mode. */
  choice: {
    question: OfferedQuestion | null;
    disabled: boolean;
    onPick: (optionIds: readonly string[]) => void;
    onOther: () => void;
    onStop: () => void;
    stopping: boolean;
  };
  /** The composer, already built: it owns the form state. Used in `text` mode. */
  composer: ReactNode;
  /** An error for the modes that have no composer to show it. */
  error: string | null;
}

/** Picks the dock's content for the mode; the `Dock` carries the input band line. */
export function RunDock({ mode, working, choice, composer, error }: RunDockProps) {
  return (
    <Dock mode={mode}>
      {mode !== "text" && error ? (
        <p role="alert" className="chat-col border-x bg-card px-5 pt-2 text-note text-destructive max-guides:px-4">
          {error}
        </p>
      ) : null}
      {mode === "busy" ? <WorkingBar {...working} /> : null}
      {mode === "choice" && choice.question ? (
        <ChoicePicker
          question={choice.question}
          disabled={choice.disabled}
          onPick={choice.onPick}
          onOther={choice.onOther}
          onStop={choice.onStop}
          stopping={choice.stopping}
        />
      ) : null}
      {mode === "text" ? composer : null}
    </Dock>
  );
}
