import "server-only";

import { cookies } from "next/headers";

import { createApiClient } from "./create-client";
import { API_ORIGIN } from "./origin";
import { WORKSPACE_COOKIE } from "./workspace";

/**
 * The API client for server components and route handlers: talks to `API_ORIGIN` directly and
 * forwards the incoming cookies (the session). A server component cannot clear the workspace
 * cookie, so a rejected workspace is cleared by the browser client on its next call.
 */
export async function getServerClient() {
  const jar = await cookies();
  const cookieHeader = jar.toString();
  return createApiClient({
    baseUrl: API_ORIGIN,
    cache: "no-store",
    headers: () => {
      const headers: Record<string, string> = {};
      if (cookieHeader) headers.cookie = cookieHeader;
      return headers;
    },
    getWorkspaceId: () => jar.get(WORKSPACE_COOKIE)?.value ?? null,
  });
}
