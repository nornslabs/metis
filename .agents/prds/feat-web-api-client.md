# PRD: feat-web-api-client

Linear: SHIP-222 · https://linear.app/heimdallabs/issue/SHIP-222/122-typed-api-client-with-cookie-sessions

Milestone: M1 — Identity and workspaces. Branch: `feat/web-api-client`. Parent: SHIP-219. Blocked by SHIP-221.

## Problem / Goal

After SHIP-221 the web can sign in, but it calls the API with hand-written `fetch`. Every later screen needs typed requests, the same headers (`X-Metis-Client`, `X-Workspace-Id`), one error shape and one reaction to an expired session. Hand-written API types drift from the server silently.

Goal: one typed `openapi-fetch` client generated from the server's OpenAPI schema, cookie-authenticated, with a typed `ApiError`, the first TanStack Query hooks, and CI that fails when web and server types drift.

## User stories

1. As a web developer, I want request and response types generated from the server, so that I never hand-write an API type.
2. As a web developer, I want one client that sets credentials and headers, so that each call site only names the route and body.
3. As a web developer, I want mutations to send `X-Metis-Client: web` automatically, so that no request fails the CSRF check by mistake.
4. As a user with several workspaces, I want every call to carry my chosen workspace, so that I see that workspace's data.
5. As a web developer, I want server components to use the same client with the incoming cookie, so that server and browser fetches behave the same.
6. As a web developer, I want every non-2xx answer as a typed `ApiError` with `code`, so that I branch on codes, not strings.
7. As a user whose session expired, I want to be sent to sign-in with a short "Signed out" notice, so that I understand why I left the page.
8. As a user, I want a failed action to show its message near the action (or a toast for background work), so that I know what failed.
9. As a web developer, I want field errors mapped to form fields, so that forms show them inline.
10. As a web developer, I want `useMe()`, `useCurrentWorkspace()` and `useWorkspaces()` hooks, so that the shell (SHIP-224) can render the user and workspaces.
11. As a maintainer, I want CI to fail when the committed schema differs from the server's, so that a server change cannot break the web unnoticed.
12. As a user, I want no `Authorization` header or token anywhere, so that the only credential is the `HttpOnly` cookie.

## Requirements

1. **Schema export.** A server command prints the OpenAPI JSON without running services (imports the FastAPI app and calls `app.openapi()`). See Open questions for where it lives.
2. **Generation.** `npm run gen:api`: `openapi-typescript` from that JSON into `web/lib/api/schema.d.ts` (committed, generated header, excluded from lint). Never hand-write API types.
3. **Client.** `web/lib/api/client.ts`: `createClient<paths>` from `openapi-fetch`.
   - Browser: base URL same origin (the `/v1` rewrite), `credentials: "include"`.
   - Server: `getServerClient()` with base URL `API_ORIGIN`, forwarding the incoming `cookie` header; `cache: "no-store"`.
   - Middleware: `POST`/`PUT`/`PATCH`/`DELETE` add `X-Metis-Client: web`; every call adds `X-Workspace-Id` from the `metis_workspace` cookie when set (browser: `document.cookie`; server: `cookies()`). Never an `Authorization` header.
4. **Workspace cookie.** `metis_workspace` (not `HttpOnly`, `SameSite=Lax`, `Path=/`, 1 year) holds the chosen workspace id. Helpers `getWorkspaceId()` / `setWorkspaceId(id)` / `clearWorkspaceId()`. A `403 auth.forbidden` answer to a call that sent the header clears the cookie (the user left or lost the workspace) and refetches, so the server falls back to the personal workspace.
5. **Errors.** Every non-2xx is parsed into `ApiError {status, code, title, detail, request_id, retryable, errors}` (problem+json shape in `server-context.md`), validated with Zod; a body that does not parse becomes `code: "common.unexpected"` with the HTTP status. `ApiError` is thrown from hooks so TanStack Query surfaces it.
6. **Session expiry.** In the browser, `auth.not_signed_in` or `auth.session_expired` → clear the query cache, toast "Signed out", `router.replace("/sign-in?redirect_to=<path>")`, once per expiry (no toast storm when several queries fail together). On the server, the same codes → `redirect("/sign-in?redirect_to=...")`.
7. **Other errors.** `auth.csrf_failed` and every other code are left to the caller; `lib/api/errors.ts` exports `fieldErrors(err)` (maps `errors[]` to `react-hook-form` `setError` input) and `errorMessage(err)` (`detail ?? title`).
8. **Hooks.** One per resource in `lib/api/queries/`, one per mutation in `lib/api/mutations/`: `useMe()` (`GET /v1/auth/me`), `useCurrentWorkspace()` (`GET /v1/workspaces/current`), `useWorkspaces()` (`GET /v1/workspaces`). Query keys include the workspace id where the route is workspace-scoped. Retry: none on 4xx, up to 2 on `retryable` 5xx.
9. **Replace `getMe()`.** SHIP-221's plain-`fetch` `getMe()` uses `getServerClient()`; the `(app)` layout guard behaves the same.
10. **CI.** In `.github/workflows/ci.yml`, a step (in the job that has both `uv` and Node) exports the schema, runs `gen:api`, and fails on `git diff --exit-code web/lib/api/schema.d.ts`.

## Out of scope

- SSE / `useRunEvents` (SHIP-235); `EventSource` does not use this client.
- Hooks for settings, keys, ideas or runs (added by the screens that need them: SHIP-224, SHIP-235).
- Any server route or error-code change.

## Touches

- `web/lib/api/` (`client.ts`, `schema.d.ts`, `errors.ts`, `workspace.ts`, `queries/`, `mutations/`)
- `web/lib/auth/get-me.ts`, `web/components/providers/` (global query error handler)
- `web/package.json` (`gen:api`), `web/eslint.config.mjs` (ignore `schema.d.ts`)
- `server/scripts/` (OpenAPI export command), `.github/workflows/ci.yml`
- `.agents/ctx/ui-context.md` (workspace cookie, error handling), `.agents/progress-tracker.md`

## Dependencies

- `feat-web-sign-in` (SHIP-221): done.

## Testing

Seam: the client module (`lib/api`) with `fetch` replaced by a fake that records requests and returns canned problem+json. Vitest. Tests check the requests the client sends and the errors it raises, not hook internals.

- Mutations carry `X-Metis-Client: web`; `GET` does not. No call carries `Authorization`.
- `X-Workspace-Id` is sent when the cookie is set and absent when not.
- 409 problem+json → `ApiError` with `code`, `status`, `request_id`; a non-JSON 500 → `common.unexpected`.
- 401 `auth.session_expired` → redirect to `/sign-in` once and one toast, for two concurrent failing queries.
- 403 `auth.forbidden` with the header → workspace cookie cleared.
- `fieldErrors` maps `errors[]` to field paths.
- End to end (Playwright, from SHIP-221's harness): `useMe()` renders the user with only the session cookie.
- CI: a deliberate server schema change without regenerating fails the drift step.

## Acceptance criteria

- [x] `useMe()` is fully typed and works with only the session cookie.
- [x] No `Authorization` header is sent anywhere.
- [x] A 401 session error redirects to `/sign-in`; a 409 surfaces as `ApiError` with `code`.
- [x] Type drift between server and web fails CI.
- [x] `npm run lint`, `typecheck`, `build` pass; Vitest tests pass.

## Open questions

None open.

## Resolved

- Workspace choice: a readable `metis_workspace` cookie, read by server components and the browser (user, 2026-11-17).
- OpenAPI export: `server/scripts/export_openapi.py` prints `app.openapi()` with no services running; it ships in this PRD (no server behaviour change) (user, 2026-11-17).
- Test seam: Vitest on `lib/api` with a fake `fetch`, plus Playwright end to end (user, 2026-11-17).

## Status

done
