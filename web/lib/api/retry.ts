import { ApiError } from "./errors";

const MAX_RETRIES = 2;

/** TanStack Query `retry`: never on 4xx; up to 2 times on a `retryable` API error or a network failure. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_RETRIES) return false;
  if (error instanceof ApiError) return error.status >= 500 && error.retryable;
  return true;
}
