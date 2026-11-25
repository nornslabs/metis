/** The query params the server adds when it sends the browser back after the Linear OAuth flow. */
const CONNECTED_PARAM = "integration";
const ERROR_PARAM = "integration_error";

export type ConnectReturn = { kind: "connected" } | { kind: "error"; code: string };

/** What the OAuth return says, or null when the URL carries no return params. */
export function readConnectReturn(search: URLSearchParams): ConnectReturn | null {
  const error = search.get(ERROR_PARAM);
  if (error !== null) return { kind: "error", code: error };
  return search.get(CONNECTED_PARAM) === "linear" ? { kind: "connected" } : null;
}

/** The same URL without the return params; other params stay. */
export function withoutConnectReturn(pathname: string, search: URLSearchParams): string {
  const next = new URLSearchParams(search);
  next.delete(CONNECTED_PARAM);
  next.delete(ERROR_PARAM);
  const query = next.toString();
  return query === "" ? pathname : `${pathname}?${query}`;
}

const FALLBACK_MESSAGE = "Linear could not be connected. Try again.";
const ERROR_MESSAGES: Readonly<Record<string, string>> = {
  "mcp.oauth_failed": "Linear did not accept the connection.",
  "mcp.oauth_state_invalid": "The connect attempt expired. Try again.",
};

/** A short sentence for an `integration_error` code. */
export function connectErrorMessage(code: string): string {
  return ERROR_MESSAGES[code] ?? FALLBACK_MESSAGE;
}

/** The path the server should bring the browser back to: this page with the Integrations tab open. */
export function connectRedirectPath(pathname: string, search: URLSearchParams): string {
  const next = new URLSearchParams(search);
  next.delete(CONNECTED_PARAM);
  next.delete(ERROR_PARAM);
  next.set("settings", "integrations");
  return `${pathname}?${next.toString()}`;
}
