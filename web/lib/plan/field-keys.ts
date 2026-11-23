import type { KeyboardEvent } from "react";

/** Esc leaves a field, so the keyboard never traps the user. */
export function blurOnEscape(event: KeyboardEvent<HTMLElement>): void {
  if (event.key === "Escape") event.currentTarget.blur();
}

/** Enter finishes a one-line field; Esc leaves it. */
export function blurOnEnterOrEscape(event: KeyboardEvent<HTMLElement>): void {
  if (event.key === "Enter") event.currentTarget.blur();
  blurOnEscape(event);
}
