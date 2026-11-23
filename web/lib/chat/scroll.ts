/** The thread follows new content only when the reader is this close to the bottom. */
export const FOLLOW_THRESHOLD_PX = 160;

/** Pixels between the bottom of the content and the bottom of the visible area. */
export function distanceFromBottom(scrollHeight: number, scrollTop: number, clientHeight: number): number {
  return scrollHeight - scrollTop - clientHeight;
}

/** True when new content should scroll into view: the reader is at the bottom, or just sent a message. */
export function shouldFollow(distance: number, justSent: boolean): boolean {
  return justSent || distance <= FOLLOW_THRESHOLD_PX;
}
