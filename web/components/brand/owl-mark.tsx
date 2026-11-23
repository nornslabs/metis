import { cn } from "@/lib/utils";

/** `working` blinks and scans, `waiting` looks down at the user, `idle` is still. */
export type OwlState = "idle" | "working" | "waiting";

export interface OwlMarkProps {
  state?: OwlState;
  /** Size and color utilities, e.g. `size-4`; the mark fills `currentColor`. */
  className?: string;
}

/** The Metis owl (ui-context.md, Brand). Decorative: the product name carries the meaning. */
export function OwlMark({ state = "idle", className }: OwlMarkProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
      data-state={state}
      className={cn("owl", className)}
    >
      <path
        fillRule="evenodd"
        d="M3 2.5 9 6h6l6-3.5V14l-9 7.5L3 14Z M8.5 7.8a3.2 3.2 0 1 0 0 6.4a3.2 3.2 0 1 0 0-6.4Z M15.5 7.8a3.2 3.2 0 1 0 0 6.4a3.2 3.2 0 1 0 0-6.4Z M10.6 15h2.8L12 17.6Z"
      />
      <g className="owl-pupils">
        <circle cx="8.5" cy="11" r="1.3" />
        <circle cx="15.5" cy="11" r="1.3" />
      </g>
      <rect className="owl-lid" x="5.2" y="7.7" width="6.6" height="6.6" />
      <rect className="owl-lid" x="12.2" y="7.7" width="6.6" height="6.6" />
    </svg>
  );
}
