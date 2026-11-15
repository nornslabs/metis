# PRD: feat-auth-sessions

Linear: SHIP-264 · https://linear.app/heimdallabs/issue/SHIP-264/12a1-sessions-auth-identities-and-current-user

Parent: SHIP-263 (12A · Server-owned auth: Google sign-in and sessions). Order: **12A.1 (this)** → 12A.2 (SHIP-265, Google sign-in) → web 12.1–12.3 → 12A.4 (SHIP-267, remove JWT).

## Problem / Goal

Today the API trusts an HS256 JWT minted by the web app with Auth.js (SHIP-216). Metis is moving sign-in to the server: the server runs Google sign-in itself and issues its own session cookie (SHIP-263). Before the Google flow (SHIP-265) can sign anyone in, the server needs two things:

1. **Server-side sessions** it can check on every request: an opaque random token in an `HttpOnly` cookie. Only its SHA-256 hash is stored. The token has a 30-day absolute expiry and a 7-day idle expiry. Revocation applies on the next request.
2. **A user model with more than one sign-in method**: `identity.auth_identities` links a user to `(provider, subject)` pairs (`google` now, `email` later), so users, sessions and route guards never change when a provider is added.

Goal: add the tables, the session service, the cookie helpers, a cookie-based auth dependency with a CSRF check, the session config and the session error codes. The existing JWT routes keep working unchanged. SHIP-267 swaps them over.

## User stories

1. As a signed-in user, I want my browser to carry an opaque `HttpOnly` session cookie, so that page scripts cannot read my credentials.
2. As a signed-in user, I want each API call with my session cookie to resolve to my user, so that I don't have to send a token by hand.
3. As a user with no session cookie, I want a 401 `auth.not_signed_in`, so that the web app sends me to sign-in.
4. As a user whose session is more than 30 days old, I want a 401 `auth.session_expired`, so that old sessions can't be used forever.
5. As a user who hasn't used Metis for 7 days, I want my session to expire (`auth.session_expired`), so that an abandoned device is signed out.
6. As an active user, I want each use to extend my idle window, so that I stay signed in while I keep working.
7. As a user who signed out, I want that session refused on the very next request, even if the server had cached it, so that signing out actually works.
8. As a user who chose "sign out everywhere", I want every one of my sessions revoked at once, so that a lost device is cut off.
9. As a user whose cookie holds a garbage or unknown token, I want a 401 `auth.session_expired`, so that the web app clears it and asks me to sign in again.
10. As a user, I want a cross-site form or script that rides on my cookie to be refused (403 `auth.csrf_failed`), so that other sites can't change my data.
11. As the web app, I want to opt in to mutations by sending `X-Metis-Client: web`, so that only Metis's own client can write with the cookie.
12. As a user, I want safe methods (`GET`, `HEAD`, `OPTIONS`) to work without the CSRF header, so that simple reads and preflights are not blocked.
13. As the web app on `http://localhost:3000`, I want CORS to allow credentials and the `X-Metis-Client` header for configured origins only, so that the browser sends my cookie to the API.
14. As an operator, I want only the token hash in the database, so that a DB leak can't be replayed as live sessions.
15. As an operator, I want the raw token and `Cookie` header never logged, so that logs can't be used to hijack sessions.
16. As an operator, I want session rejections logged with a reason (`missing`, `unknown`, `expired`, `idle`, `revoked`, `csrf`), so that I can debug sign-in problems.
17. As an operator, I want session lookups cached in Redis, so that every API call doesn't hit Postgres for auth.
18. As an operator, I want auth to keep working, slower, if Redis is down, so that a cache outage doesn't sign everyone out.
19. As an operator, I want `last_seen_at` written at most once per 5 minutes per session, so that auth doesn't add a DB write to every request.
20. As an operator, I want cookies `Secure` in every environment except local development, and an optional `COOKIE_DOMAIN`, so that the cookie works behind real domains and on `localhost`.
21. As an operator, I want session lifetime, idle window and cookie name in config, so that I can tune them without code changes.
22. As an operator, I want each session to record its user agent and IP, so that a future "your devices" view and incident review have data.
23. As an existing user (signed up through Auth.js), I want my account to get a Google auth identity from my existing `auth_sub`, so that my first server-side Google sign-in (SHIP-265) finds my account instead of creating a new one.
24. As a future email-sign-in user, I want my identities modelled per provider, so that one user can sign in with Google or email.
25. As a developer of SHIP-265, I want `create_session`, `resolve_session`, `logout` and `logout_all` service functions plus cookie helpers, so that the login, callback and logout routes stay thin.
26. As a developer of SHIP-267, I want a ready `session_user` dependency, so that the cutover is a dependency swap and a rename.
27. As a maintainer, I want HTTP-seam tests for valid, missing, unknown, expired, idle, revoked (cached and uncached) sessions, CSRF and hash-only storage, so that auth regressions fail CI.

## Requirements

1. **Migration `0006_auth_sessions`** (`identity` schema, owner role; `metis_app` picks up DML through the default privileges from `0004_app_role`. Verify this and add explicit grants if not):
   - `identity.auth_identities`: `id uuid pk`, `user_id uuid not null → identity.users(id) on delete cascade`, `provider text not null check (provider in ('google','email'))`, `subject text not null`, `email text not null`, `email_verified boolean not null default false`, `created_at timestamptz not null default now()`, `last_login_at timestamptz null`, `unique(provider, subject)`, index on `user_id`.
   - `identity.sessions`: `id uuid pk`, `user_id uuid not null → identity.users(id) on delete cascade`, `token_hash bytea not null unique`, `created_at`, `last_seen_at`, `expires_at timestamptz not null`, `revoked_at timestamptz null`, `user_agent text null`, `ip inet null`, index on `user_id`.
   - **No RLS** on either table. They are not tenant tables, and only the identity module reads them.
   - **Backfill**: one `auth_identities` row per existing `identity.users` row: `provider='google'`, `subject=users.auth_sub`, `email=users.email`, `email_verified=true`, `created_at=users.created_at`. Keep `users.auth_sub` (SHIP-267 drops it). The issue calls the column `auth_subject`; the real column is `auth_sub`.
   - Downgrade drops both tables.
2. **`core/security.py`** (new; holds no JWT code. `core/auth.py` stays until SHIP-267):
   - `SESSION_TOKEN_BYTES = 32`; `new_session_token() -> str` (`secrets.token_urlsafe(32)`).
   - `hash_session_token(token: str) -> bytes`: SHA-256 digest of the UTF-8 token.
   - `set_session_cookie(response, token)` / `clear_session_cookie(response)`: name `SESSION_COOKIE_NAME`, `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure=settings.cookie_secure`, `Domain=COOKIE_DOMAIN` when set, `Max-Age = SESSION_TTL_DAYS` in seconds. Clearing uses the same name, path and domain.
3. **Redis client** (`core/redis.py`, new): one app-lifetime `Redis` from `REDIS_URL`, exposed as a FastAPI dependency `RedisDep` (overridable in tests) and closed in the app lifespan. `core/events.py` is unchanged.
4. **`modules/identity/sessions_repo.py`** (new). Postgres and Redis access for sessions; nothing outside identity imports it:
   - `insert_session(...)`, `get_session_by_hash(hash)`, `touch_session(id, now)`, `revoke_session(hash, now)`, `revoke_user_sessions(user_id, now) -> list[bytes]` (returns the revoked hashes).
   - Cache key `auth:session:{hex(token_hash)}`, JSON `{session_id, user_id, expires_at, last_seen_at}`, TTL `min(60 s, seconds until expires_at)`. Only active sessions are cached. Revoking deletes the cache key(s) after the DB update, so revocation applies on the next request.
   - Redis errors on read or write are logged (`auth.session_cache_unavailable`) and fall back to Postgres. They never fail the request.
5. **`modules/identity/auth_service.py`** (new). Takes the caller's `AsyncSession` and `Redis` and never commits (same contract as `service.py`):
   - `create_session(session, redis, user_id, user_agent, ip) -> NewSession(token, session_id, expires_at)`: `expires_at = now + SESSION_TTL_DAYS`, `last_seen_at = now`.
   - `resolve_session(session, redis, token) -> ActiveSession(session_id, user_id, expires_at)`: hash → cache → Postgres. Unknown → `SessionExpiredError`. The same error applies when `revoked_at` is set, when `now ≥ expires_at`, or when `now − last_seen_at ≥ SESSION_IDLE_DAYS`. Each case logs its own reason. When `last_seen_at` is older than `SESSION_TOUCH_INTERVAL` (named constant, 5 min), writes `last_seen_at = now` and refreshes the cache entry.
   - `logout(session, redis, token) -> None`: revoke that session; unknown or already-revoked is a no-op.
   - `logout_all(session, redis, user_id) -> int`: revoke every active session of the user; returns the count.
   - Also exported: `get_signed_in_user(session, user_id) -> CurrentUser` (user DTO + personal workspace, via the existing identity service).
6. **`modules/identity/auth_deps.py`** (new; in identity, not `core`, because `core` never imports a module):
   - `session_user(request, session, redis) -> SessionUser` (`CurrentUser` fields + `session_id`). Steps:
     1. Read the `SESSION_COOKIE_NAME` cookie. If it is missing or empty, raise `NotSignedInError`.
     2. Run the CSRF check. For `POST`, `PUT`, `PATCH` and `DELETE`, the request must carry `X-Metis-Client: web` exactly, otherwise raise `CsrfError`.
     3. Call `resolve_session`.
     4. Load the user, then bind `user_id` (and `session_id`) into the structlog context.
   - `SessionUserDep = Annotated[SessionUser, Depends(session_user)]`; exported from `metis.modules.identity`.
   - No existing route uses it in this PRD. SHIP-267 renames it to `current_user`, rebuilds `current_workspace` on it and removes the JWT dependency.
7. **Config** (`core/config.py`, `.env.example`, compose if needed):
   - `SESSION_COOKIE_NAME` (default `metis_session`), `SESSION_TTL_DAYS` (default 30), `SESSION_IDLE_DAYS` (default 7; validated `1 ≤ idle ≤ ttl`), `COOKIE_DOMAIN` (optional, default unset), `COOKIE_SECURE` (optional bool; unset ⇒ `not is_development`; exposed as `settings.cookie_secure`), `WEB_BASE_URL` (default `http://localhost:3000`).
   - `WEB_BASE_URL` replaces the unused `PUBLIC_BASE_URL` (remove the field and its `.env.example` line).
8. **Errors** (`core/errors.py`): `NotSignedInError` → `auth.not_signed_in` 401, `SessionExpiredError` → `auth.session_expired` 401, `CsrfError` → `auth.csrf_failed` 403. All are RFC 7807 via the existing handlers. They don't carry `WWW-Authenticate: Bearer`, which stays specific to the JWT path. `auth.unauthorized` / `auth.token_expired` stay until SHIP-267.
9. **CORS** (`entrypoints/api.py`): `allow_credentials=True` (origins stay the explicit `CORS_ORIGINS` list; never `*`), and add `X-Metis-Client` to the allowed headers. The bearer path is unaffected.
10. **Logging**: never log the raw token, the `Cookie` header or `Set-Cookie`. Rejections log `auth.session_rejected` at `info` with `reason` ∈ `missing`, `unknown`, `expired`, `idle`, `revoked`, `csrf`, plus `session_id` when known.
11. **Docs sync**:
    - `server-context.md`: session auth section, config table, error codes, the `auth:session:*` Redis key, `session_user`, the CSRF header rule, and the CORS change.
    - `architecture.md`: Auth row and Auth and Access Model. Note the transition: the cookie session is the target, and JWT stays until SHIP-267.
    - `.env.example`.

## Out of scope

- Google sign-in, the `AuthProvider` protocol, `/v1/auth/*` routes, and setting or clearing the cookie on login and logout (SHIP-265).
- Switching any existing route from JWT to the session, deleting `core/auth.py`, removing `AUTH_JWT_*`, and dropping `users.auth_sub` (SHIP-267).
- Writing `auth_identities` rows for users created through the JWT path after this migration (SHIP-265 links by verified email, so they are still found).
- Clearing the cookie automatically on `auth.session_expired` responses.
- Email sign-in, magic links, and a "your devices" UI.
- Rate limiting, session rotation on privilege change, and cleanup of expired session rows.

## Touches

- `server/migrations/versions/0006_auth_sessions.py` (new)
- `server/metis/core/security.py` (new), `server/metis/core/redis.py` (new), `server/metis/core/config.py`, `server/metis/core/errors.py`, `server/metis/entrypoints/api.py` (CORS, Redis lifespan)
- `server/metis/modules/identity/`:
  - New: `sessions_repo.py`, `auth_service.py`, `auth_deps.py`
  - Changed: `models.py` (ORM rows), `schemas.py` (session DTOs), `__init__.py` (exports)
- `server/tests/modules/identity/test_auth_sessions_api.py` (new), `server/tests/modules/identity/conftest.py` + `api_helpers.py` (Redis fixture, truncate list), `server/tests/core/test_config.py` (new settings)
- `.env.example`, `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`

## Dependencies

- `feat-identity-workspaces` (SHIP-214), `feat-jwt-auth` (SHIP-216), `feat-provider-keys` (SHIP-217): done.
- No blocked-by issues inside 12A; this one starts first.
- Blocks: SHIP-265 (12A.2 Google sign-in).

## Test seam

One seam, the same as SHIP-216: **HTTP requests against the FastAPI app** (`httpx.AsyncClient` + `ASGITransport`).

Setup:
- Real Postgres migrated to head, with the request session as `metis_app`.
- Real Redis on `TEST_REDIS_URL` (default `localhost:6379/15`), flushed per test.
- Tests skip only when either service is unreachable or not migrated.
- Two **test-only probe routes** are mounted on the app during the run: `GET /test/session` and `POST /test/session`. Both depend on `SessionUserDep` and return `{user_id, session_id}`.
- Sessions are created through `auth_service.create_session` in a fixture. Expiry is driven by updating `expires_at` / `last_seen_at` / `revoked_at` rows, not by mocking the clock.

Assertions cover status codes, RFC 7807 `code`s and bodies. There are two exceptions: one DB check (hash-only storage) and one log capture (no raw token).

Planned tests:

- Valid cookie → `GET` 200 with the right `user_id`.
- No cookie → 401 `auth.not_signed_in`. Unknown or garbage token → 401 `auth.session_expired`.
- `expires_at` in the past → 401 `auth.session_expired`.
- `last_seen_at` older than 7 days → 401 `auth.session_expired`. Older than 5 min (but under 7 days) → 200, and `last_seen_at` is advanced. Under 5 min → 200, and `last_seen_at` is unchanged.
- `logout` then request → 401, both with the session cached (a request first, so it is in Redis) and uncached.
- `logout_all` revokes every session of the user (cached ones included) and leaves another user's sessions working.
- `POST` without `X-Metis-Client` → 403 `auth.csrf_failed`. With `X-Metis-Client: other` → 403. With `X-Metis-Client: web` → 200. `GET` without it → 200.
- Hash-only storage: `identity.sessions.token_hash` equals SHA-256(token), and the raw token appears in no column of the row.
- No raw token in logs: capture structlog output across create, resolve, reject and logout, and assert the token string never appears.
- Redis unreachable (client override pointing at a closed port) → valid cookie still 200 via Postgres.
- Migration backfill: a user inserted before upgrade gets a `google` identity with `subject = auth_sub` (run as a migration test, or by asserting on the seeded test DB after `alembic upgrade head`).
- `create_session` sets `expires_at ≈ now + 30 d`. `set_session_cookie` emits `HttpOnly`, `SameSite=Lax`, `Path=/`, and `Secure` when `COOKIE_SECURE=true` (checked through a probe route that sets the cookie).
- CORS preflight from a `CORS_ORIGINS` origin requesting `X-Metis-Client` → allowed, with `Access-Control-Allow-Credentials: true`.
- Config: `SESSION_IDLE_DAYS > SESSION_TTL_DAYS` fails validation. `COOKIE_SECURE` unset ⇒ `False` in development and `True` otherwise.
- Existing JWT tests still pass unchanged.

## Acceptance criteria

- [x] A valid session cookie resolves to its user. Expired, idle or revoked sessions return `auth.session_expired`.
- [x] Only the token hash is stored. The raw token never appears in the DB or logs (test).
- [x] A mutation without `X-Metis-Client` returns `auth.csrf_failed`.
- [x] Revoking a session takes effect on the next request even when it was cached.
- [x] `auth_identities` and `sessions` exist with no RLS. Existing users are backfilled with a `google` identity.
- [x] `SESSION_COOKIE_NAME`, `SESSION_TTL_DAYS`, `SESSION_IDLE_DAYS`, `COOKIE_DOMAIN`, `COOKIE_SECURE` and `WEB_BASE_URL` are in `Settings` and `.env.example`, and `PUBLIC_BASE_URL` is removed.
- [x] CORS allows credentials and `X-Metis-Client` for `CORS_ORIGINS` only.
- [x] Existing JWT routes and tests are unchanged and pass.
- [x] `server-context.md` and `architecture.md` describe sessions, the CSRF rule and the transition.
- [x] `uv run ruff check`, `uv run mypy` and `uv run pytest` pass.

## Open questions

None. Resolved 2026-11-14 (see Decisions in `progress-tracker.md`):

1. **Dependency location and name**: `modules/identity/auth_deps.py`, as `session_user` / `SessionUserDep`. Not `core/auth_deps.py`, because `core` never imports a module. No route uses it yet; SHIP-267 renames it to `current_user` and swaps routes.
2. **Test seam**: HTTP through the ASGI client, with test-only probe routes, real Postgres (`metis_app`) and real Redis. Expiry is driven by editing rows.
3. **Cache and touch**: Redis cache TTL 60 s (capped at `expires_at`). Revoke deletes the key. `last_seen_at` is written at most once per 5 min.
4. **Config and CORS**: `WEB_BASE_URL` replaces the unused `PUBLIC_BASE_URL`. CORS gets `allow_credentials=True` and the `X-Metis-Client` header in this PRD.

Defaults taken without asking (from the issue or existing patterns):
- Unknown or garbage tokens return `auth.session_expired`, not `not_signed_in`.
- The CSRF check runs after the missing-cookie check.
- Backfilled identities are `google` with `email_verified=true`, because Auth.js Google was the only sign-in path.
- `ip` is stored as `inet`.
- The plan file `plans/server-auth-google.md` named in the issue's Agent notes is not in the repo, so this PRD relies on the issue text.

## Review follow-ups (2026-11-14)

Two-axis review (standards + spec). Fixed:

- **Revocation race:** a request that read the session from Postgres before a logout committed could re-cache it as active for 60 s. Revoking now writes a tombstone `auth:session:revoked:{hex hash}` (TTL 120 s = 2 × cache TTL) and deletes the entry, and readers check the tombstone first. A test replays the stale write after revocation.
- `CORS_ORIGINS` containing `*` now fails settings validation, because credentialed CORS must never allow any origin.
- A corrupt cache entry is logged (`auth.session_cache_corrupt`), not silently dropped.
- `auth_service` is no longer exported from `metis.modules.identity` (the module's public API stays `service.py` plus the deps).
- `get_session_user(session, active) -> SessionUser` replaces the tuple-returning `get_signed_in_user`. `SessionUser` is a frozen model in `schemas.py`.
- Rejection reasons are the `SessionRejection` enum.
- Added a `Secure` cookie test.

Deviations from the requirements above, kept on purpose:

- `create_session(session, user_id, user_agent, ip)` takes no `redis` because nothing is cached at creation.
- The raw setting is `cookie_secure: bool | None` (env name `COOKIE_SECURE`). The derived value is `settings.secure_cookies`, because pydantic-settings maps env vars by field name.
- The cache entry is `SessionRecord` (`id`, `user_id`, `expires_at`, `last_seen_at`, `revoked_at`).
- Probe routes live under `/v1/_test/`, following the SHIP-216 pattern.

Not changed:

- There are no mocked-repository unit tests. The agreed seam is HTTP only (Decisions, 2026-11-14).
- Probe routes are mounted at import time, as in `test_identity_api.py`.
- `auth_identities.provider` stays text + CHECK with no enum until SHIP-265 uses it.

## Status

done
