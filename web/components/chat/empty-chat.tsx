"use client";

import { ArrowUp } from "lucide-react";
import { useId, useState } from "react";

import { CrossTick } from "@/components/frame/cross-tick";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const SUGGESTIONS = [
  "A habit tracker for remote teams",
  "AI tutor for spoken Spanish",
  "Marketplace for used lab equipment",
] as const;

const COLUMN_LEFT = "left-[calc(50%-var(--col)/2)]";
const COLUMN_RIGHT = "left-[calc(50%+var(--col)/2)]";
const FRAME_LEFT = "left-[calc(50%-var(--frame)/2)]";
const FRAME_RIGHT = "left-[calc(50%+var(--frame)/2)]";
const BAND = "top-0";

/**
 * The empty chat: title, suggestions and the composer. The composer is not wired yet (the idea
 * chat, SHIP-235, submits it); chips only fill the box and Send stays disabled.
 */
export function EmptyChat() {
  const [text, setText] = useState("");
  const inputId = useId();

  return (
    <>
      <section className="flex flex-1 flex-col items-center justify-center gap-1.5 px-5 py-8 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">
          What are you building?
        </h1>
        <p className="max-w-lead text-body text-muted-foreground">
          Describe your idea in a sentence or two. Metis will ask a few
          questions, research the market and score it.
        </p>
      </section>
      <div className="mx-auto flex w-(--col) shrink-0 flex-wrap justify-center gap-1.5 px-5 pb-3 max-guides:px-4">
        {SUGGESTIONS.map((suggestion) => (
          <Button
            key={suggestion}
            type="button"
            variant="outline"
            className="h-6 px-2 text-xs"
            onClick={() => setText(suggestion)}
          >
            {suggestion}
          </Button>
        ))}
      </div>
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
          onSubmit={(event) => event.preventDefault()}
          className="mx-auto w-(--col) border-x bg-card px-5 pt-3 pb-2 max-guides:px-4"
        >
          <label htmlFor={inputId} className="sr-only">
            Your idea
          </label>
          <textarea
            id={inputId}
            rows={1}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Describe your idea…"
            className="max-h-45 min-h-5.5 w-full resize-none bg-transparent py-0.5 text-body outline-none placeholder:text-muted-foreground"
          />
          <div className="flex items-center justify-end gap-2 pt-1">
            <kbd className="font-mono text-eyebrow text-muted-foreground max-compact:hidden">
              Enter to send
            </kbd>
            <Tooltip>
              <TooltipTrigger
                render={
                  <Button
                    type="submit"
                    size="icon-xs"
                    aria-label="Send"
                    disabled
                    className="size-6.5"
                  />
                }
              >
                <ArrowUp size={14} strokeWidth={2.5} />
              </TooltipTrigger>
              <TooltipContent>Send</TooltipContent>
            </Tooltip>
          </div>
        </form>
      </div>
    </>
  );
}
