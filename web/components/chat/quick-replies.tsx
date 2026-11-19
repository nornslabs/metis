import { Button } from "@/components/ui/button";
import { QUICK_REPLIES } from "@/lib/schemas/answer";

interface QuickRepliesProps {
  disabled: boolean;
  onReply: (value: string) => void;
  /** Stops the run: it waits for an answer, so Stop is not the send button here. */
  onStop: () => void;
  stopping: boolean;
}

/** "Skip" and "That's enough" send at once; "Stop run" ends the run that waits for an answer. */
export function QuickReplies({ disabled, onReply, onStop, stopping }: QuickRepliesProps) {
  return (
    <div role="group" aria-label="Quick replies" className="flex flex-wrap items-center gap-1.5 pb-2">
      {QUICK_REPLIES.map((reply) => (
        <Button
          key={reply.value}
          type="button"
          variant="outline"
          className="h-6 px-2 text-xs"
          disabled={disabled}
          onClick={() => onReply(reply.value)}
        >
          {reply.label}
        </Button>
      ))}
      <Button type="button" variant="ghost" className="ml-auto h-6 px-2 text-xs" disabled={stopping} onClick={onStop}>
        {stopping ? "Stopping…" : "Stop run"}
      </Button>
    </div>
  );
}
