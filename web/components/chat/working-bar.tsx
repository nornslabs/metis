import { Square } from "lucide-react";

import { OwlMark } from "@/components/brand/owl-mark";
import { TypingDots } from "@/components/chat/typing-dots";
import { Button } from "@/components/ui/button";

interface WorkingBarProps {
  /** What Metis is doing now, e.g. "Researching… Web search". */
  label: string;
  /** "2/3", or null before the first step. */
  counter: string | null;
  onStop: () => void;
  stopping: boolean;
}

/** The dock while Metis works: owl badge, shimmering step, counter and Stop (ui-context.md, WorkingBar). */
export function WorkingBar({ label, counter, onStop, stopping }: WorkingBarProps) {
  return (
    <div className="chat-col relative flex h-11.5 items-center gap-2.5 border-x bg-card px-5 max-guides:px-4">
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-px working-sweep motion-reduce:hidden"
      />
      <span aria-hidden="true" className="grid size-5.5 shrink-0 place-items-center border">
        <OwlMark state="working" className="size-4" />
      </span>
      <span className="min-w-0 flex-1 truncate text-control font-medium text-shimmer">{label}</span>
      <TypingDots label={label} />
      {counter ? <span className="font-mono text-eyebrow text-muted-foreground">{counter}</span> : null}
      <Button type="button" variant="outline" size="sm" disabled={stopping} onClick={onStop}>
        <Square size={10} fill="currentColor" aria-hidden="true" />
        {stopping ? "Stopping…" : "Stop"}
      </Button>
    </div>
  );
}
