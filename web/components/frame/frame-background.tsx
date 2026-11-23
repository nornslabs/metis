import { SideRails } from "./side-rails";

/** Fixed background layer: side rails and the bordered safe area. Lines and ticks: `GridGuides`. */
export function FrameBackground() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 bg-background"
    >
      <SideRails />
      <div
        data-frame="safe"
        className="absolute inset-y-0 left-1/2 w-(--frame) -translate-x-1/2 border-x bg-background max-compact:w-full max-compact:border-x-0"
      />
    </div>
  );
}
