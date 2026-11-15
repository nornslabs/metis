# PRD: refactor-remove-jwt-auth

Linear: SHIP-267 · https://linear.app/heimdallabs/issue/SHIP-267/12a4-remove-jwt-auth-from-the-api-and-update-docs

Parent: SHIP-263 (12A · Server-owned auth: Google sign-in and sessions). Order: 12A.1 (SHIP-264, done) → 12A.2 (SHIP-265, done) → web 12.1–12.3 (SHIP-221, SHIP-224) → **12A.4 (this)**.

## Problem / Goal

The API still has two ways to authenticate. Every `/v1` route checks an HS256 JWT (`Authorization: Bearer`, `core/auth.py`), and only `/v1/auth/logout-all` uses the server session cookie that SHIP-264/265 built. As a result:
- the server carries a shared JWT secret that nothing should mint any more;
- `identity.users.auth_sub` duplicates data that `identity.auth_identities` already holds;
- the docs describe two auth models.

Goal: cut over fully to server sessions.
- Every protected route resolves its user through the session cookie: `session_user` becomes `current_user`, and `current_workspace` is rebuilt on top of it.
- JWT verification, `AUTH_JWT_*` config, the JWT error code and `users.auth_sub` are removed.
- The context docs describe only the session model.

## User stories

1. As a signed-in user, I want every API call to authenticate with my session cookie, so that I sign in once with Google and the whole app works.
2. As a signed-in user, I want `GET /v1/me` to return my user, workspaces and current workspace from my session, so that the app shell shows who I am.
3. As a signed-in user, I want `X-Workspace-Id` to keep choosing my workspace (personal workspace when absent), so that switching workspaces behaves exactly as before.
4. As a signed-in user who isn't a member of a workspace, I want a 403 for that workspace (same as an unknown id), so that nobody can probe which workspaces exist.
5. As a visitor with no cookie, I want every protected route to return 401 `auth.not_signed_in`, so that the web app can send me to the sign-in page.
6. As a user whose session expired, went idle or was revoked, I want 401 `auth.session_expired` on every protected route, so that the web app asks me to sign in again.
7. As a user, I want a cookie-authenticated mutation without `X-Metis-Client: web` refused with 403 `auth.csrf_failed`, so that another site can't act on my behalf.
8. As a user, I want a `Authorization: Bearer` header to be ignored entirely, so that an old or stolen API token grants nothing.
9. As an owner, I want provider keys and workspace settings routes to keep their owner-only rules under the session user, so that the cutover changes nothing about who can spend the workspace's money.
10. As a member, I want RLS to scope every tenant query to my current workspace exactly as before, so that I never see another workspace's data.
11. As an operator, I want `AUTH_JWT_SECRET` and `AUTH_JWT_AUDIENCE` gone from settings, `.env.example`, compose and CI, so that there is no unused shared secret to leak or rotate.
12. As an operator, I want the API to start without any JWT config, so that a fresh `.env` from `.env.example` boots.
13. As an operator, I want an old `.env` that still has `AUTH_JWT_*` to boot without errors, so that removing the setting doesn't break running deployments.
14. As an operator, I want `identity.users.auth_sub` dropped by a migration, so that sign-in identity lives only in `auth_identities`.
15. As an operator, I want the migration to downgrade cleanly (column restored from the Google identities), so that a rollback is possible.
16. As an operator, I want 401 responses to carry no `WWW-Authenticate: Bearer` challenge, so that clients aren't told to send a token the server no longer accepts.
17. As an operator, I want no route left without auth by accident, so that a forgotten dependency can't expose data.
18. As a developer, I want one parametrized test over the app's route table that checks every protected route returns `auth.not_signed_in` without a cookie, so that a new route that forgets auth fails CI.
19. As a developer, I want an explicit allowlist of public routes (`/v1/health`, `/v1/auth/*`), so that making a route public is a visible, reviewed choice.
20. As a developer, I want `grep -ri "jwt\|AUTH_JWT" server/` to find only the Google `id_token` check, so that I can tell at a glance that JWT auth is gone.
21. As a developer, I want test helpers that sign a user in by creating a real session and setting its cookie, so that API tests exercise the same auth path as production.
22. As a developer, I want `current_user` / `CurrentUserDep` to keep their names and import path from `metis.modules.identity`, so that new routes don't need to know about the migration.
23. As a developer, I want `SessionUser` to be the single "signed-in caller" type (`user`, `personal_workspace`, `session_id`), so that there aren't two near-identical caller types.
24. As a developer, I want SSE (`GET /v1/runs/{id}/events`) planned on the session cookie, with no `POST /runs/{id}/stream-token`, so that live events need no second token scheme.
25. As an agent reading the docs, I want `architecture.md`, `server-context.md` and the AGENTS.md folder tree to describe only session auth, so that I don't build against the removed JWT model.

## Requirements

1. **Swap route auth to sessions** (`modules/identity/auth_deps.py`, `deps.py`, `__init__.py`):
   - Rename `session_user` → `current_user` and `SessionUserDep` → `CurrentUserDep`. The return type is `SessionUser` (remove the old `CurrentUser` dataclass). Keep the check order: no cookie → `auth.not_signed_in`; mutation without `X-Metis-Client: web` → `auth.csrf_failed`; unresolvable session → `auth.session_expired`.
   - Rebuild `current_workspace` / `CurrentWorkspaceDep` on the new `current_user`. Keep its behaviour unchanged: `X-Workspace-Id` header, personal workspace when absent, 422 for a non-UUID, 403 for non-member or unknown, then `set_user` + `set_workspace` + `bind_context`.
   - Keep one module for the auth dependencies: fold `deps.py` into `auth_deps.py`, or the other way round. `metis.modules.identity` exports `current_user`, `current_workspace`, `CurrentUserDep`, `CurrentWorkspaceDep` and `check_csrf`.
   - All identity routes (`/v1/me`, `/v1/workspaces`, `/v1/settings*`) and `/v1/auth/logout-all` use the new dependencies.
2. **Delete JWT verification**: remove `core/auth.py` (`bearer_claims`, `TokenClaims`, `JWT_ALGORITHM`, `CLOCK_SKEW_SECONDS`) and every import of it. Afterwards PyJWT is imported only in `modules/identity/providers/google.py` (`id_token` check) and test fakes. `pyjwt` stays as a dependency.
3. **Remove now-unused identity code**:
   - `service.upsert_user_from_claims`, `repo.upsert_user` and `repo.get_user_by_auth_sub`.
   - The `users.auth_sub` lookup in `auth_service._find_user_to_link`. Sign-in becomes: `(provider, subject)`, else email, else create.
   - The `sub` field of `UserClaims`, if it then has no other use.
   - `repo.insert_user` no longer writes `auth_sub`.
4. **Config**:
   - Remove `auth_jwt_secret` / `auth_jwt_audience` from `Settings`, together with their required-field validation and their entry in the redaction list.
   - Remove `AUTH_JWT_SECRET` / `AUTH_JWT_AUDIENCE` from `.env.example`, `compose.yaml` (shared env block), `.github/workflows/ci.yml` and `server/tests/conftest.py`.
   - Stale `AUTH_JWT_*` env vars must not fail settings loading. Check the `extra` policy, and add a test.
5. **Migration `0007_drop_users_auth_sub`**:
   - Drop `uq_users_auth_sub` and `identity.users.auth_sub`.
   - Downgrade re-adds the column as nullable, backfills it from each user's `google` identity `subject`, then restores NOT NULL and the unique constraint.
   - Update the ORM model (`models.py`). Merged migrations `0003` and `0006` stay untouched.
6. **Errors**:
   - Remove `ErrorCode.TOKEN_EXPIRED` (`auth.token_expired`), its catalog entry and `TokenExpiredError`.
   - Remove the `WWW-Authenticate: Bearer` challenge: `_BEARER_CHALLENGE_CODES` in `core/error_handlers.py`.
   - Session failures use the SHIP-264 codes: `auth.not_signed_in`, `auth.session_expired`, `auth.csrf_failed`.
   - The issue's `auth.missing_token` / `auth.invalid_token` never existed. JWT failures used `auth.unauthorized` (`AuthError`). For the fate of `AuthError` / `auth.unauthorized`, see Open question 1.
7. **SSE plan**: no `POST /v1/runs/{id}/stream-token`. The docs say `GET /v1/runs/{id}/events` authenticates with the session cookie (same-site `EventSource` with credentials) and `current_workspace`.
8. **API entrypoint**: update the docstring and comments in `entrypoints/api.py`. They currently say JWT auth.
9. **Docs sync**:
   - `architecture.md`:
     - The Auth row of the stack table becomes server sessions only.
     - The "Today: … Auth.js … HS256 JWT" bullet goes away.
     - The SHIP-263 "Target" bullet becomes the current model.
   - `server-context.md`:
     - Configuration table: remove the JWT row.
     - Auth and Request Scope: remove the `core/auth.py` and web-minted-token bullets, and describe `current_user` / `current_workspace` on sessions.
     - Remove `upsert_user_from_claims` from the identity service contract.
     - `sign_in` no longer has the `auth_sub` step.
     - API Conventions: the Auth row becomes the session cookie + `X-Metis-Client: web` for mutations + `X-Workspace-Id`, and SSE uses the cookie.
     - Error table: remove `auth.token_expired`.
   - `AGENTS.md` folder tree: refresh it to match the repo. `server/` holds `metis/` (with `adapters/`, `core/`, …) and `migrations/`, and the tree marks no auth files as JWT. This is an explicitly instructed change.
   - The Notion LLD and API spec are updated separately (issue Agent notes) and are not part of this PRD.

## Out of scope

- Web app changes: the sign-in page, app shell and removing Auth.js (SHIP-221, SHIP-224). The web app doesn't currently send `Authorization: Bearer` or read `AUTH_JWT_*`, so removing them breaks nothing there.
- Building the SSE endpoint (only its auth plan is documented).
- New auth features: email sign-in, session rotation, a "your devices" list, rate limiting.
- Notion LLD / API spec updates.
- Removing `pyjwt` (still used for Google `id_token`s).
- Editing merged migrations.

## Touches

- `server/metis/core/`:
  - Deleted: `auth.py`
  - Changed: `config.py`, `errors.py`, `error_handlers.py`, `__init__.py`
- `server/metis/modules/identity/`: `auth_deps.py`, `deps.py` (merged or removed), `__init__.py`, `api.py`, `auth_api.py`, `auth_service.py`, `service.py`, `repo.py`, `models.py`, `schemas.py`
- `server/metis/entrypoints/api.py` (docstring and comments)
- `server/migrations/versions/0007_drop_users_auth_sub.py` (new)
- `server/tests/`:
  - `conftest.py`, `core/test_config.py`, `core/test_errors.py`
  - `modules/identity/`: `api_helpers.py`, `conftest.py`, `test_identity_api.py`, `test_provider_keys_api.py`, `test_identity_service.py`, `test_auth_sessions_api.py`, `test_auth_google_api.py`, `session_probe.py` (if the probe routes are no longer needed)
  - New: `test_route_auth.py`
- `.env.example`, `compose.yaml`, `.github/workflows/ci.yml`
- `.agents/ctx/architecture.md`, `.agents/ctx/server-context.md`, `AGENTS.md`

## Dependencies

- `feat-auth-sessions` (SHIP-264): done.
- `feat-auth-google` (SHIP-265): done.
- Linear blocked-by: SHIP-224 (12.3, app shell on server sessions), which has no PRD yet and is still Todo. **The user decided on 2026-11-14 to proceed without it.** The web app doesn't use the API JWT, so the server cutover is safe on its own.

## Test seam

Use the existing single seam, the same one as SHIP-216/217/264/265: **HTTP requests against the real FastAPI app** (`httpx.AsyncClient` + `ASGITransport`), with real Postgres as `metis_app` and real Redis on `TEST_REDIS_URL`. No new seams.

- **Sign-in helper** (`api_helpers.py`): create a user (+ personal workspace) and a session through the identity services (`auth_service.create_session`), then return a client or cookies carrying the session cookie and `X-Metis-Client: web`. This replaces `make_token` / `bearer`. Existing identity and provider-key API tests switch to it and keep their assertions.
- **Route-table test** (`test_route_auth.py`): one parametrized test over `app.routes` (every `/v1` `APIRoute` × method), minus an explicit `PUBLIC_ROUTES` allowlist (`/v1/health`, `/v1/auth/providers`, `/v1/auth/google/login`, `/v1/auth/google/callback`, `/v1/auth/logout`). Each route is called with no cookie and must return 401 `auth.not_signed_in`. Path parameters get placeholder values.
- Other planned tests:
  - `Authorization: Bearer <valid old-style HS256 token>` with no cookie → 401 `auth.not_signed_in`.
  - 401 responses carry no `WWW-Authenticate` header.
  - `/v1/me` with a session → user + workspaces.
  - `X-Workspace-Id`: other member workspace → 200 and RLS-scoped data; non-member and unknown → 403; non-UUID → 422; absent → personal.
  - Expired or revoked session → `auth.session_expired`.
  - Mutation without `X-Metis-Client` → `auth.csrf_failed`.
  - Google sign-in tests: the `auth_sub` linking test is removed. The email-link and subject paths still pass.
  - Config: settings load without `AUTH_JWT_*`, and with stale `AUTH_JWT_*` in the env.
  - Migration: upgrade drops the column, and downgrade restores it from the Google identities. This runs in the existing migration test, if one exists, or as a round-trip check in the identity conftest.

## Acceptance criteria

- [x] `grep -riE "jwt|AUTH_JWT" server/ --exclude-dir=.venv` finds only `modules/identity/providers/google.py`, Google test fakes, `pyproject.toml`/`uv.lock` (PyJWT) and the tests that prove old JWT config and tokens are ignored (`tests/core/test_config.py`, `tests/modules/identity/test_route_auth.py`).
- [x] Every protected route returns 401 `auth.not_signed_in` without a cookie (one parametrized test over the route table; public routes are an explicit allowlist).
- [x] Workspace scoping (`X-Workspace-Id`, RLS) works unchanged with the session user. The existing identity and provider-key API tests pass on sessions.
- [x] A Bearer token alone grants nothing. No 401 carries `WWW-Authenticate: Bearer`.
- [x] `AUTH_JWT_SECRET` / `AUTH_JWT_AUDIENCE` are gone from `Settings`, `.env.example`, `compose.yaml` and CI. The API boots without them.
- [x] Migration `0007` drops `identity.users.auth_sub` and downgrades cleanly.
- [x] `auth.token_expired` and `TokenExpiredError` are removed. Session errors use the SHIP-264 codes.
- [x] `architecture.md`, `server-context.md` and the AGENTS.md folder tree describe session auth only. SSE is documented on the cookie, with no stream token.
- [x] `uv run ruff check`, `uv run mypy` and `uv run pytest` pass.

## Open questions

None. Resolved 2026-11-14 (see Decisions in `progress-tracker.md`):

1. **`AuthError` / `auth.unauthorized`**: keep both as the generic 401, used for Starlette 401s, with no Bearer challenge. Delete only `auth.token_expired` / `TokenExpiredError`.
2. **Test seam**: one HTTP seam with a session-cookie sign-in helper that replaces the JWT helpers, plus a parametrized route-table test with an explicit public-route allowlist. Confirmed.

Defaults taken without asking (from the issue or existing patterns):
- The issue's `identity.users.auth_subject` is the `auth_sub` column, and "JWT verification in `core/security.py`" is `core/auth.py`. `core/security.py` keeps the session and PKCE helpers.
- `session_user` is renamed rather than wrapped, so there is a single `current_user`.
- `upsert_user_from_claims` is deleted, not kept for tests. Service tests create users through `repo.insert_user` / `sign_in`.

## Review follow-ups (2026-11-15)

Two-axis review (standards + spec). Fixed:

- The route-table test walks `fastapi.routing.iter_route_contexts(app.routes)`, so routes hidden from the OpenAPI schema are covered too.
- The Bearer test sends a real HS256 token signed like the old web-minted one.
- New `test_downgrade_restores_auth_sub_from_google_identities` replays `0007`'s `RESTORE_SQL` in a rolled-back transaction.
- One `google_profile` test helper in `api_helpers.py`. Test subjects are `google-*`, not Auth.js-style `auth|*`.
- `Settings.__repr__` masks the fields in a `SECRET_FIELDS` constant.

Decided with the user:

- **Destructive `0007` drop:** kept, as an explicit exception to "backward-compatible migrations only" (`code-standards.md`). Metis is pre-launch: there is no production data and no rolling deploy. Recorded in Decisions.

Beyond the spec, kept on purpose:

- `EmailTakenError` was removed. It was dead once `upsert_user_from_claims` went, because sign-in now links accounts by email. No error code was removed, since it used `common.conflict`.
- `Authorization` was dropped from the CORS allowed headers, because nothing reads it any more (user story 8).
- The identity `client` fixture now points Redis at the test DB, because every route resolves sessions. `http` is kept as an alias.
- The downgrade fills a user with no Google identity with `user:<id>`, so that NOT NULL and the unique constraint can be restored.

Not changed:

- `auth_deps.py` holds both `current_user` and `current_workspace`. Requirement 1 asked for one auth-dependency module.
- `core/__init__.py` needed no change: it never exported the JWT pieces.
- The tracked file is `Agents.md`; `AGENTS.md` resolves to it on macOS. Not renamed here.

## Status

done
