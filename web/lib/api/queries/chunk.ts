/** The summaries routes accept at most this many idea ids per call. */
export const SUMMARY_IDS_MAX = 50;

/** Splits `items` into pages of at most `size`, in order. */
export function chunk<T>(items: readonly T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let start = 0; start < items.length; start += size) chunks.push(items.slice(start, start + size));
  return chunks;
}
