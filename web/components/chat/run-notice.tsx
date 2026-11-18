import { CircleAlert, MessageCircleQuestion } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import type { RunError, RunInterrupt } from "@/lib/events/schemas";

interface RunErrorRowProps {
  error: RunError;
  action?: ReactNode;
}

/** A failed run: the reason inline, with the code for support, and Retry. */
export function RunErrorRow({ error, action }: RunErrorRowProps) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-x-2 gap-y-1 border border-destructive/40 px-2.5 py-1.5">
      <CircleAlert size={14} aria-hidden="true" className="text-destructive" />
      <span className="text-body">{error.message}</span>
      <code className="font-mono text-meta text-muted-foreground">{error.code}</code>
      {action ? <span className="ml-auto">{action}</span> : null}
    </div>
  );
}

interface StartRunButtonProps {
  label: string;
  pending: boolean;
  onClick: () => void;
}

export function StartRunButton({ label, pending, onClick }: StartRunButtonProps) {
  return (
    <Button type="button" variant="outline" size="sm" disabled={pending} onClick={onClick}>
      {pending ? "Starting…" : label}
    </Button>
  );
}

/** A question or approval the run waits on. Answering comes with the interview chat (SHIP-239). */
export function InterruptPlaceholder({ interrupt }: { interrupt: RunInterrupt }) {
  return (
    <div className="flex flex-col gap-1 border px-2.5 py-2">
      <span className="flex items-center gap-1.5 text-meta font-medium text-muted-foreground uppercase tracking-label">
        <MessageCircleQuestion size={13} aria-hidden="true" />
        {interrupt.kind === "question" ? "Metis asks" : "Needs your approval"}
      </span>
      <p className="text-body whitespace-pre-wrap">{interrupt.text}</p>
      <p className="text-meta text-muted-foreground">Answering in the chat is coming soon.</p>
    </div>
  );
}

/** A quiet one-line status in the agent message (stopped, finished). */
export function RunNote({ children }: { children: ReactNode }) {
  return <p className="text-control text-muted-foreground">{children}</p>;
}
