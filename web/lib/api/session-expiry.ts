import { isSessionError } from "./errors";

/**
 * Runs `onExpired` once for a burst of session errors (several queries failing together),
 * until `rearm()` is called (a request succeeded, so the session is back).
 */
export function createSessionExpiryHandler(initialOnExpired: () => void = () => undefined) {
  let armed = true;
  let onExpired = initialOnExpired;
  return {
    /** Swaps the action (the provider supplies the router once it is mounted). */
    setOnExpired(next: () => void): void {
      onExpired = next;
    },
    handle(error: unknown): void {
      if (!armed || !isSessionError(error)) return;
      armed = false;
      onExpired();
    },
    rearm(): void {
      armed = true;
    },
  };
}
