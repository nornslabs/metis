import { Button } from "@/components/ui/button";
import { describeError } from "@/lib/api/errors";

interface LoadFailureProps {
  what: string;
  error: unknown;
  onRetry: () => void;
  className?: string;
}

/** An inline alert for a query that failed, with Retry. */
export function LoadFailure({ what, error, onRetry, className }: LoadFailureProps) {
  return (
    <div role="alert" className={`flex flex-wrap items-center gap-2 border border-destructive/40 px-2.5 py-1.5 ${className ?? ""}`.trim()}>
      <span className="text-control">
        Could not load the {what}. {describeError(error)}
      </span>
      <Button type="button" variant="outline" size="sm" className="ml-auto" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}
