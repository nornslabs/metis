"use client";

import { ArrowUp, Square } from "lucide-react";
import { useId, type FormEvent, type KeyboardEvent, type Ref, type TextareaHTMLAttributes } from "react";

import { CrossTick } from "@/components/frame/cross-tick";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const COLUMN_LEFT = "left-[calc(50%-var(--col)/2)]";
const COLUMN_RIGHT = "left-[calc(50%+var(--col)/2)]";
const FRAME_LEFT = "left-[calc(50%-var(--frame)/2)]";
const FRAME_RIGHT = "left-[calc(50%+var(--frame)/2)]";
const BAND = "top-0";

/** `send` submits the form; `stop` and `stopping` replace it while a run is active. */
export type ComposerAction = "send" | "stop" | "stopping";

export interface ComposerProps {
  /** Props for the textarea, e.g. from `register("text")`; `ref` included. */
  textarea: TextareaHTMLAttributes<HTMLTextAreaElement> & { ref?: Ref<HTMLTextAreaElement> };
  label: string;
  action: ComposerAction;
  canSend: boolean;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onStop?: () => void;
  /** Inline error under the textarea (validation or API). */
  error?: string | null;
}

/** Enter sends, Shift+Enter (or an IME composition) types a new line. */
function submitOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
  if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
  event.preventDefault();
  event.currentTarget.form?.requestSubmit();
}

function ActionButton({ action, canSend, onStop }: Pick<ComposerProps, "action" | "canSend" | "onStop">) {
  const isSend = action === "send";
  const label = isSend ? "Send" : action === "stop" ? "Stop" : "Stopping…";
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            type={isSend ? "submit" : "button"}
            size="icon-xs"
            aria-label={label}
            disabled={isSend ? !canSend : action === "stopping"}
            onClick={isSend ? undefined : onStop}
            className="size-6.5"
          />
        }
      >
        {isSend ? <ArrowUp size={14} strokeWidth={2.5} /> : <Square size={10} fill="currentColor" />}
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

/**
 * The prompt input in the band at the bottom of the chat column: auto-growing textarea, hint and
 * a send button that becomes Stop while a run is active (ui-context.md, Composer).
 */
export function Composer({ textarea, label, action, canSend, onSubmit, onStop, error }: ComposerProps) {
  const inputId = useId();
  const errorId = `${inputId}-error`;
  const hint = action === "stopping" ? "Stopping…" : "Enter to send";

  return (
    <div className="relative shrink-0 border-t">
      <span aria-hidden="true" className="max-guides:hidden">
        <CrossTick className={`${COLUMN_LEFT} ${BAND}`} />
        <CrossTick className={`${COLUMN_RIGHT} ${BAND}`} />
      </span>
      <span aria-hidden="true" className="max-compact:hidden">
        <CrossTick className={`${FRAME_LEFT} ${BAND}`} />
        <CrossTick className={`${FRAME_RIGHT} ${BAND}`} />
      </span>
      <form
        noValidate
        onSubmit={onSubmit}
        className="mx-auto w-(--col) border-x bg-card px-5 pt-3 pb-2 focus-within:ring-1 focus-within:ring-ring focus-within:ring-inset max-guides:px-4"
      >
        <label htmlFor={inputId} className="sr-only">
          {label}
        </label>
        <textarea
          rows={1}
          {...textarea}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          onKeyDown={submitOnEnter}
          className="field-sizing-content max-h-45 min-h-5.5 w-full resize-none bg-transparent py-0.5 text-body outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
        />
        {error ? (
          <p id={errorId} role="alert" className="pt-1 text-note text-destructive">
            {error}
          </p>
        ) : null}
        <div className="flex items-center justify-end gap-2 pt-1">
          <kbd aria-live="polite" className="font-mono text-eyebrow text-muted-foreground max-compact:hidden">
            {hint}
          </kbd>
          <ActionButton action={action} canSend={canSend} onStop={onStop} />
        </div>
      </form>
    </div>
  );
}
