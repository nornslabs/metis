/** Three staggered breathing dots for active thinking/working states. */
export function TypingDots({ label = "Metis is working" }: { label?: string }) {
  return (
    <span role="status" aria-label={label} className="inline-flex h-5 items-center gap-1">
      <span aria-hidden="true" className="size-1.5 rounded-full bg-muted-foreground typing-dot" />
      <span
        aria-hidden="true"
        className="size-1.5 rounded-full bg-muted-foreground typing-dot [animation-delay:160ms]"
      />
      <span
        aria-hidden="true"
        className="size-1.5 rounded-full bg-muted-foreground typing-dot [animation-delay:320ms]"
      />
    </span>
  );
}
