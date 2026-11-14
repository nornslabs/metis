# PRD: feat-jwt-auth

Linear: SHIP-216 · https://linear.app/heimdallabs/issue/SHIP-216/10-jwt-auth-workspace-scoping-and-me

## Problem / Goal

The API has no authentication. Anyone can call it, nothing knows who the caller is, and no request runs inside a workspace, so the RLS policies built in SHIP-214 never apply to real traffic. Every later feature (provider keys, ideas, MCP connections, the web app shell) needs an authenticated user and one workspace per request.

Goal: every `/v1` route except `/v1/health` requires a valid Auth.js-issued JWT. A verified token becomes an identity user with a personal workspace. Each request is scoped to one workspace, chosen with `X-Workspace-Id` (default: the personal workspace), checked for membership and enforced by Postgres RLS. Three routes expose this: `GET /v1/me`, `GET /v1/workspaces` and `POST /v1/workspaces`. CORS allows only the configured web origins.

## User stories

1. As a signed-in user, I want my API calls to carry my Auth.js JWT as a bearer token, so that the server knows who I am without its own login.
2. As a user calling the API with no token, I want a 401 problem response, so that the web app knows to send me to sign-in.
3. As a user with an expired token, I want a 401 with code `auth.token_expired`, so that the web app can refresh my session instead of showing an error.
4. As a user with a token signed by someone else, or for another audience, I want it rejected with 401, so that forged tokens cannot reach my data.
5. As a user whose clock is a few seconds off, I want 30 s of leeway on `exp`/`iat`/`nbf`, so that I am not signed out by clock skew.
6. As a first-time user, I want my first API call to create my user record and personal workspace, so that I can start right away.
7. As a returning user, I want later calls to reuse my user and personal workspace and refresh my name and image, so that my data stays in one place.
8. As a user, I want requests without `X-Workspace-Id` to run in my personal workspace, so that single-user use needs no setup.
9. As a team member, I want to send `X-Workspace-Id` to work in a team workspace I belong to, so that I can switch between workspaces.
10. As a user, I want a workspace I am not a member of to be refused with 403, so that I cannot read other teams' data.
11. As a user, I want a workspace id that does not exist to get the same 403 as a foreign one, so that nobody can probe which workspaces exist.
12. As a user, I want a malformed `X-Workspace-Id` to get a 422, so that client bugs are obvious.
13. As a user, I want `GET /v1/me` to return my profile, all my workspaces with my role, and the current workspace, so that the web app can render the shell and workspace switcher in one call.
14. As a user, I want `GET /v1/workspaces` to list my workspaces with my role, so that I can pick one.
15. As a user, I want `POST /v1/workspaces` with a name to create a workspace I own, so that I can start a team space.
16. As a user, I want a blank or too-long workspace name rejected with 422, so that I get a clear validation error.
17. As a developer of later modules, I want `current_user` and `current_workspace` FastAPI dependencies, so that every new route gets auth and workspace scoping by declaring one parameter.
18. As a developer, I want the request's DB session to already have `app.workspace_id` (and `app.user_id`) set, so that RLS-scoped queries just work and a forgotten scope fails closed.
19. As a developer, I want the request session committed on success and rolled back on error, so that a failed request leaves no half-written rows.
20. As an operator, I want the API to connect as a non-superuser role, so that RLS is actually enforced in every environment, not only in tests.
21. As the web app (`http://localhost:3000`), I want CORS to allow my origin with `Authorization` and `X-Workspace-Id` headers, so that the browser can call the API.
22. As an operator, I want any other origin refused by CORS, so that other sites cannot use a user's browser against the API.
23. As an operator, I want tokens and the JWT secret never logged, and auth failures logged with a reason, so that I can debug sign-in problems safely.
24. As a maintainer, I want HTTP-level tests with locally signed JWTs (no token, bad audience, expired, foreign workspace, valid request with RLS active), so that auth regressions fail CI.

## Requirements

1. **Token verification** (`core/auth.py`):
   - Read `Authorization: Bearer <jwt>`. Missing header, wrong scheme or empty token → `AuthError` (`auth.unauthorized`, 401).
   - Verify with `AUTH_JWT_SECRET`, algorithm **HS256 only** (reject `none` and any other `alg`), `aud == AUTH_JWT_AUDIENCE`, `exp` required, 30 s leeway (named constant).
   - Expired → new `TokenExpiredError` (`auth.token_expired`, 401). Every other failure (bad signature, wrong audience, malformed, missing `exp`) → `AuthError` (`auth.unauthorized`, 401). The `detail` never echoes the token.
   - Claims used: `sub` (required), `email` (required), `name` (optional), `picture` (optional; Auth.js name for the image). Missing `sub`/`email`, or claims identity rejects (e.g. a malformed email), → 401. Return a frozen `TokenClaims` model.
   - Uses `PyJWT`; nothing outside `core/auth.py` imports it.
2. **Request session dependency** (`core/db.py`): one `AsyncSession` per request, shared by all auth dependencies and the route; commits after the route returns successfully, rolls back on any exception.
3. **RLS helper** (`core/db.py`): `set_workspace(session, workspace_id)` and `set_user(session, user_id)` set `app.workspace_id` / `app.user_id` with `set_config(..., true)` (transaction-local). Identity's `repo.rls_context` keeps working unchanged.
4. **`current_user` dependency** (`modules/identity/deps.py`, exported from `metis.modules.identity`, so `core` never imports a module; `core/auth.py` only verifies the token): verify the token, then in the request session call `identity.upsert_user_from_claims(sub, email, name, picture)` and `identity.ensure_personal_workspace(user)`. Returns a `CurrentUser` holding the `User` DTO and the personal `Workspace`. Calls identity only via its public exports. `EmailTakenError` from identity surfaces as its 409.
5. **`current_workspace` dependency**: depends on `current_user`. Reads `X-Workspace-Id`:
   - absent → personal workspace;
   - not a UUID → `InvalidInputError` (422);
   - not in `identity.list_workspaces(user)` (unknown or foreign) → `PermissionDeniedError` (`auth.forbidden`, 403).
   Then calls `set_workspace(session, workspace.id)` and `set_user(session, user.id)` on the request session and returns the caller's `Membership` (workspace + role). Binds `workspace_id` and `user_id` into the structlog context; the middleware clears them.
6. **Routes** (`modules/identity/api.py`, router prefix `/v1`, all require `current_workspace` or `current_user`):
   - `GET /v1/me` → `200 {user, workspaces: [{workspace, role}], current_workspace: {workspace, role}}`.
   - `GET /v1/workspaces` → `200 {items: [{workspace, role}], next_cursor: null}` (list convention; no pagination yet).
   - `POST /v1/workspaces` body `{name}` → `201 {workspace, role: "owner"}` via `identity.create_workspace`.
   Response models live in `modules/identity/schemas.py`; handlers stay thin (parse, call one service, return schema).
7. **Router wiring** (`entrypoints/api.py`): include the identity router. `/v1/health` and `/` stay public. Any later `/v1` router must depend on `current_user`/`current_workspace` (documented in `server-context.md`).
8. **CORS** (`entrypoints/api.py`): `CORSMiddleware` with `allow_origins=settings.get_cors_origins()` (the existing `CORS_ORIGINS` setting; the issue's `CORS_ORIGIN` is the same thing), `allow_credentials=False` (bearer tokens, no cookies), methods `GET, POST, PUT, PATCH, DELETE, OPTIONS`, headers `Authorization, Content-Type, X-Workspace-Id, Idempotency-Key, X-Request-ID`, expose `X-Request-ID`. No wildcard.
9. **Non-superuser app role**: migration `0004_app_role` creates `metis_app` (`NOSUPERUSER NOBYPASSRLS`) with DML and default privileges on `core` and `identity`. When `APP_DB_PASSWORD` is set while migrating, the role gets `LOGIN` with that password. Compose sets it and points the api/worker/scheduler `DATABASE_URL` at `metis_app`, so RLS applies to real requests. Outside compose, `DATABASE_URL` is whatever the developer sets.
10. **Errors**: add `TokenExpiredError` (`auth.token_expired`) to `core/errors.py`; reuse `AuthError`, `PermissionDeniedError`, `InvalidInputError`. All responses are RFC 7807 via the existing handlers. 401 responses carry `WWW-Authenticate: Bearer`.
11. **Logging**: never log the token, the `Authorization` header or the secret. Log auth failures at `info` with a reason code (`missing`, `expired`, `invalid`, `claims`), not the claims.
12. **Docs sync**: `server-context.md` (auth dependencies, `X-Workspace-Id` rule, identity routes, `TokenExpiredError`, request-session commit rule, `metis_app`), `architecture.md` (Auth: JWT HS256 + aud + leeway, workspace resolution, app role), `.env.example`/README if the DB URL or role setup changes.

## Out of scope

- Web sign-in UI and the Auth.js config that mints the token (SHIP-219).
- API keys / machine tokens.
- Adding members, invites, role changes, leaving or deleting workspaces over HTTP (identity services exist; routes come later).
- Pagination of `/v1/workspaces` beyond `next_cursor: null`.
- Token revocation, refresh, or JWE (encrypted) tokens.
- Rate limiting of auth failures.

## Touches

`server/metis/core/auth.py` (new), `server/metis/core/db.py`, `server/metis/core/error_handlers.py`, `server/metis/core/middleware.py`, `server/metis/modules/identity/deps.py` (new), `server/metis/modules/identity/repo.py` + `service.py` (RLS setting helpers moved to `core/db.py`), `server/metis/core/errors.py`, `server/metis/modules/identity/api.py` (new), `server/metis/modules/identity/schemas.py` (response models), `server/metis/modules/identity/__init__.py` (export router), `server/metis/entrypoints/api.py`, `server/pyproject.toml` + `uv.lock` (JWT library via `uv add`), app-role migration `server/migrations/versions/0004_app_role.py` (new), `compose.yaml`, `server/tests/conftest.py` (32+ byte test secret), `server/tests/modules/identity/test_identity_api.py` (new), `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`, `.env.example`, `README.md`.

## Dependencies

- `feat-identity-workspaces` (SHIP-214): done. Provides `upsert_user_from_claims`, `ensure_personal_workspace`, `list_workspaces`, `create_workspace` and the `identity.members` RLS policies.
- `chore-core-errors` (SHIP-261), `fix-foundation-gaps` (SHIP-262): done. RFC 7807 handlers, `request_id`, fail-closed RLS helper.
- Blocks: SHIP-217 (provider keys), SHIP-218 (ideas), SHIP-219 (web sign-in), SHIP-231 (MCP connections).

## Test seam

One seam, the highest available: **HTTP requests against the FastAPI app** (`httpx.AsyncClient` with `ASGITransport`), with JWTs signed locally in the test using the test `AUTH_JWT_SECRET`/`AUTH_JWT_AUDIENCE` from `tests/conftest.py`, on a real Postgres migrated to head. The request session runs as a non-superuser role so RLS is real (same pattern as `tests/core/test_rls.py` and `tests/modules/identity/test_identity_service.py`: `TEST_DATABASE_URL`, skip only when Postgres is unreachable or not migrated, truncate `identity` tables per test). Tests assert status codes, RFC 7807 `code` values and response bodies only; no tests call `core/auth.py` internals directly (every case, including `alg: none`, is sent over HTTP).

Planned tests:

- No `Authorization` header → 401 `auth.unauthorized`, `WWW-Authenticate: Bearer`.
- Wrong scheme / garbage token / wrong secret → 401 `auth.unauthorized`.
- Wrong audience → 401 `auth.unauthorized`.
- Expired beyond 30 s → 401 `auth.token_expired`; expired within 30 s → 200.
- `alg: none`, RS256 and HS512 headers → 401.
- Email already owned by another account → 409 `common.conflict`.
- Missing `sub` or `email` claim → 401.
- First `GET /v1/me` → user, one personal workspace (role `owner`), `current_workspace` = personal; second call creates nothing new and updates the name.
- `X-Workspace-Id` of another user's workspace → 403 `auth.forbidden`; random UUID → 403; `not-a-uuid` → 422.
- `X-Workspace-Id` of a workspace the user belongs to → 200 with that `current_workspace`.
- RLS active: inside a request scoped to workspace A, `identity.members` rows of workspace B are not visible (checked through a test-only route or by asserting `current_setting('app.workspace_id')` and member visibility via the request session).
- `POST /v1/workspaces` → 201, owner role, appears in `GET /v1/workspaces`; blank name → 422.
- `/v1/health` without a token → 200.
- CORS preflight from `CORS_ORIGINS` origin → allowed with `X-Workspace-Id`; from another origin → no `Access-Control-Allow-Origin`.
- A route that raises after writing → nothing persisted (rollback).

## Acceptance criteria

- [x] All `/v1` routes except `/v1/health` require a valid JWT (HS256, `aud`, `exp`, 30 s leeway); failures are RFC 7807 401s.
- [x] `GET /v1/me` returns the user, their workspaces with roles, and the current workspace.
- [x] `GET /v1/workspaces` and `POST /v1/workspaces` work for the signed-in user.
- [x] `X-Workspace-Id` selects the workspace (default personal); non-members get 403.
- [x] Requests are RLS-scoped to the chosen workspace, enforced by a non-superuser DB role.
- [x] CORS allows only `CORS_ORIGINS`.
- [x] Tests listed above pass with locally signed JWTs.
- [x] `server-context.md` and `architecture.md` describe the auth dependencies and workspace resolution.
- [x] `uv run ruff check`, `uv run mypy`, `uv run pytest` pass.

## Open questions

None. Resolved 2026-11-14 (see Decisions in `progress-tracker.md`):

1. JWT library: `PyJWT`, added with `uv add pyjwt`; imported only in `core/auth.py`.
2. Non-superuser role: included in this PRD. `metis_app` (`LOGIN NOSUPERUSER NOBYPASSRLS`) with grants and default privileges on `core` and `identity`; the api/worker `DATABASE_URL` uses it, and migrations keep the owner role.
3. Token format: HS256-signed JWS only. SHIP-219 makes the web app mint a short-lived HS256 API token with `AUTH_JWT_SECRET`/`AUTH_JWT_AUDIENCE`; the server never decrypts Auth.js JWEs.
4. Test seam: HTTP only (ASGI client, locally signed JWTs, real migrated Postgres, non-superuser role). No unit tests on `core/auth.py` internals.

## Review follow-ups (2026-11-14)

Applied after the two-axis code review:

- `0004_app_role` runs the quoted `ALTER ROLE … PASSWORD` as raw driver SQL, so a password containing `:word` no longer breaks the migration or leaks into its error.
- The RLS test now proves workspace scoping: Ada owns Personal and Team, Bob is a member of Team; Bob's Team row is invisible from Ada's Personal scope and visible from Team scope.
- Added RS256-header and email-taken (409) tests; the test imports `SessionDep` from `core.db`.
- `identity.repo` no longer re-exports the RLS setting names; `service.py` imports them from `core.db`.

Not changed: tests stay at the agreed HTTP seam (no mocked-service controller tests); `create_workspace` keeps returning `Workspace`, and the route builds the owner `Membership`; `GET /v1/workspaces` depends on `current_user` only, so it ignores `X-Workspace-Id`; the test-only probe routes are mounted on the app object during the test run.

## Status

done
