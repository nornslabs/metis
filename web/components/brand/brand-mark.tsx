import { OwlMark, type OwlState } from "./owl-mark";

/** The owl in the 20px filled square that leads the header on every page. */
export function BrandMark({ state }: { state?: OwlState }) {
  return (
    <span aria-hidden="true" className="grid size-5 place-items-center bg-primary text-primary-foreground">
      <OwlMark state={state} className="size-3.75" />
    </span>
  );
}
