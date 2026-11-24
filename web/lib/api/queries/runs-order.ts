/** The newest page comes first from the API; the chat reads oldest first. */
export function oldestFirst<T>(newestFirst: readonly T[]): T[] {
  return [...newestFirst].reverse();
}

/** The run whose message carries the output cards: the oldest one, which did the work. */
export function outputsRunId(runsOldestFirst: readonly { readonly id: string }[]): string | null {
  return runsOldestFirst[0]?.id ?? null;
}
