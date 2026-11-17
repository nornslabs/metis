export const WORKSPACE_COOKIE = "metis_workspace";
export const WORKSPACE_HEADER = "X-Workspace-Id";

const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

/** Reads the workspace id from a `Cookie` header string (`a=1; metis_workspace=…`). */
export function parseWorkspaceCookie(cookieHeader: string): string | null {
  for (const part of cookieHeader.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === WORKSPACE_COOKIE) {
      const value = decodeURIComponent(rest.join("="));
      return value === "" ? null : value;
    }
  }
  return null;
}

/** Not `HttpOnly` on purpose: the browser client reads it to send `X-Workspace-Id`. */
export function serializeWorkspaceCookie(id: string | null): string {
  const attributes = "Path=/; SameSite=Lax";
  if (id === null) return `${WORKSPACE_COOKIE}=; Max-Age=0; ${attributes}`;
  return `${WORKSPACE_COOKIE}=${encodeURIComponent(id)}; Max-Age=${ONE_YEAR_SECONDS}; ${attributes}`;
}

/** The chosen workspace id in the browser, or null (also null outside a browser). */
export function getWorkspaceId(): string | null {
  if (typeof document === "undefined") return null;
  return parseWorkspaceCookie(document.cookie);
}

export const WORKSPACE_CHANGED_EVENT = "metis:workspace-changed";

export function setWorkspaceId(id: string): void {
  document.cookie = serializeWorkspaceCookie(id);
  window.dispatchEvent(new Event(WORKSPACE_CHANGED_EVENT));
}

export function clearWorkspaceId(): void {
  document.cookie = serializeWorkspaceCookie(null);
  window.dispatchEvent(new Event(WORKSPACE_CHANGED_EVENT));
}
