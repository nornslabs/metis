import { ShieldQuestion } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { RunInterrupt } from "@/lib/events/schemas";

interface ApprovalPromptProps {
  interrupt: RunInterrupt;
  disabled: boolean;
  onDecide: (approved: boolean) => void;
}

/** The run asks to write to an outside tool: the action, its details and Approve / Reject. */
export function ApprovalPrompt({ interrupt, disabled, onDecide }: ApprovalPromptProps) {
  return (
    <div role="group" aria-label="Approval needed" className="flex flex-col gap-1.5 border px-2.5 py-2">
      <span className="flex items-center gap-1.5 text-meta font-medium text-muted-foreground uppercase tracking-label">
        <ShieldQuestion size={13} aria-hidden="true" />
        Needs your approval
      </span>
      <p className="text-body whitespace-pre-wrap">{interrupt.text}</p>
      {interrupt.details ? (
        <p className="text-control break-words whitespace-pre-wrap text-muted-foreground">{interrupt.details}</p>
      ) : null}
      <div className="flex gap-1.5">
        <Button type="button" size="sm" disabled={disabled} onClick={() => onDecide(true)}>
          Approve
        </Button>
        <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => onDecide(false)}>
          Reject
        </Button>
      </div>
    </div>
  );
}
