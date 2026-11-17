/** The user's message: a filled block on the right (ui-context.md, UserBubble). */
export function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1.5">
      <div className="max-w-[80%] bg-secondary px-2.5 py-1.5 text-body break-words whitespace-pre-wrap">
        {text}
      </div>
    </div>
  );
}
