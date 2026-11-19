import { CircleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { KEY_GATE_NOTICE_ID } from "@/components/chat/key-gate-notice";
import { Button } from "@/components/ui/button";
import type { RunError } from "@/lib/events/schemas";

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
  /** Blocked by the key gate: disabled, and described by the gate's line. */
  blocked?: boolean;
}

export function StartRunButton({ label, pending, onClick, blocked = false }: StartRunButtonProps) {
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      disabled={pending || blocked}
      aria-describedby={blocked ? KEY_GATE_NOTICE_ID : undefined}
      onClick={onClick}
    >
      {pending ? "Starting…" : label}
    </Button>
  );
}

/** A quiet one-line status in the agent message (stopped, finished). */
export function RunNote({ children }: { children: ReactNode }) {
  return <p className="text-control text-muted-foreground">{children}</p>;
}
