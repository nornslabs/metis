/** The body of a successful call. `ApiError` is thrown for non-2xx, so a missing body is a bug. */
export function bodyOf<T>(result: { data?: T }): T {
  if (result.data === undefined) throw new Error("The API answered without a body.");
  return result.data;
}
