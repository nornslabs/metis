/** The first value of a query parameter that may repeat. */
export function firstParam(
  value: string | readonly string[] | undefined,
): string | undefined {
  return typeof value === "string" ? value : value?.[0];
}
