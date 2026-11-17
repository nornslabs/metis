import { cn } from "@/lib/utils";

/** A 9×9 `+` mark where two lines cross; position it with `className`. */
export function CrossTick({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "absolute z-10 size-tick -translate-x-1/2 -translate-y-1/2",
        "before:absolute before:top-0 before:left-1 before:h-tick before:w-px before:bg-muted-foreground/60",
        "after:absolute after:top-1 after:left-0 after:h-px after:w-tick after:bg-muted-foreground/60",
        className,
      )}
    />
  );
}
