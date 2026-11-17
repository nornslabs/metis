import createClient, { type Middleware } from "openapi-fetch";

import { parseApiError } from "./errors";
import type { paths } from "./schema";
import { WORKSPACE_HEADER } from "./workspace";

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const CLIENT_HEADER = "X-Metis-Client";
const FORBIDDEN_CODE = "auth.forbidden";

export type ApiClientOptions = {
  baseUrl: string;
  /** Resolves the chosen workspace id for each request (cookie in the browser, `cookies()` on the server). */
  getWorkspaceId: () => string | null | Promise<string | null>;
  /** Called when the API refuses the workspace this call named (the user left it). */
  onWorkspaceRejected?: () => void;
  credentials?: RequestCredentials;
  /** Headers added to every request, e.g. the incoming `cookie` on the server. */
  headers?: () => HeadersInit | Promise<HeadersInit>;
  fetch?: typeof fetch;
  cache?: RequestCache;
};

/**
 * The one `openapi-fetch` client: sets credentials and headers, and throws `ApiError` for every
 * non-2xx answer. Never sets `Authorization`: the session cookie is the only credential.
 */
export function createApiClient(options: ApiClientOptions) {
  const middleware: Middleware = {
    async onRequest({ request }) {
      for (const [name, value] of new Headers(await options.headers?.())) {
        request.headers.set(name, value);
      }
      if (MUTATING_METHODS.has(request.method)) request.headers.set(CLIENT_HEADER, "web");
      const workspaceId = await options.getWorkspaceId();
      if (workspaceId) request.headers.set(WORKSPACE_HEADER, workspaceId);
      return request;
    },
    async onResponse({ request, response }) {
      if (response.ok) return undefined;
      const error = await parseApiError(response.clone());
      if (error.code === FORBIDDEN_CODE && request.headers.has(WORKSPACE_HEADER)) {
        options.onWorkspaceRejected?.();
      }
      throw error;
    },
  };

  const client = createClient<paths>({
    baseUrl: options.baseUrl,
    credentials: options.credentials,
    cache: options.cache,
    fetch: options.fetch,
  });
  client.use(middleware);
  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;
