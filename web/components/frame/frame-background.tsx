import { CrossTick } from "./cross-tick";
import { SideRails } from "./side-rails";

const FRAME_LEFT = "left-[calc(50%-var(--frame)/2)]";
const FRAME_RIGHT = "left-[calc(50%+var(--frame)/2)]";
const HEADER_LINE = "top-(--header-h)";
const FOOTER_LINE = "top-[calc(100%-var(--footer-h))]";

/** Fixed background layer: side rails, bordered safe area and the `+` ticks where lines cross. */
export function FrameBackground() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 bg-background"
    >
      <SideRails />
      <div className="absolute inset-y-0 left-1/2 w-(--frame) -translate-x-1/2 border-x bg-background max-compact:w-full max-compact:border-x-0" />
      <div className="max-compact:hidden">
        <CrossTick className={`${FRAME_LEFT} ${HEADER_LINE}`} />
        <CrossTick className={`${FRAME_RIGHT} ${HEADER_LINE}`} />
        <CrossTick className={`${FRAME_LEFT} ${FOOTER_LINE}`} />
        <CrossTick className={`${FRAME_RIGHT} ${FOOTER_LINE}`} />
      </div>
    </div>
  );
}
