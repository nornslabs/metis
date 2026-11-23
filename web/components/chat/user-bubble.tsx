import { Check } from "lucide-react";

interface UserBubbleProps {
  text: string;
  /** True for an answer picked from options: a check icon marks it. */
  picked?: boolean;
}

/** The user's message: a filled block on the right (ui-context.md, UserBubble). */
export function UserBubble({ text, picked = false }: UserBubbleProps) {
  return (
    <div className="flex justify-end motion-safe:animate-in motion-safe:duration-250 motion-safe:fade-in motion-safe:slide-in-from-bottom-1.5">
      <div className="flex max-w-[80%] items-center gap-1.5 bg-secondary px-2.5 py-1.5 text-body break-words whitespace-pre-wrap">
        {picked ? <Check size={12} strokeWidth={2.5} aria-label="Picked" className="shrink-0 text-muted-foreground" /> : null}
        {text}
      </div>
    </div>
  );
}
