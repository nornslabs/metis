import { CrossTick } from "./cross-tick";

const GUIDE_LEFT = "left-[calc(50%-var(--col)/2)]";
const GUIDE_RIGHT = "left-[calc(50%+var(--col)/2)]";
const HEADER_LINE = "top-(--header-h)";
const FOOTER_LINE = "top-[calc(100%-var(--footer-h))]";

/** Column guides at the chat column's edges, full height, with `+` ticks at the header and footer lines. */
export function GridGuides() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 max-guides:hidden"
    >
      <span className={`absolute inset-y-0 w-px bg-border ${GUIDE_LEFT}`} />
      <span className={`absolute inset-y-0 w-px bg-border ${GUIDE_RIGHT}`} />
      <CrossTick className={`${GUIDE_LEFT} ${HEADER_LINE}`} />
      <CrossTick className={`${GUIDE_RIGHT} ${HEADER_LINE}`} />
      <CrossTick className={`${GUIDE_LEFT} ${FOOTER_LINE}`} />
      <CrossTick className={`${GUIDE_RIGHT} ${FOOTER_LINE}`} />
    </div>
  );
}
