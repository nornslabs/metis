# PRD: feat-auth-google

Linear: SHIP-265 · https://linear.app/heimdallabs/issue/SHIP-265/12a2-google-sign-in-provider-and-auth-routes

Parent: SHIP-263 (12A · Server-owned auth: Google sign-in and sessions). Order: 12A.1 (SHIP-264, done) → **12A.2 (this)** → web 12.1–12.3 (SHIP-221, SHIP-219) → 12A.4 (SHIP-267, remove JWT).

## Problem / Goal

SHIP-264 gave the server sessions, auth identities and a cookie-based `session_user` dependency, but nothing can create a session yet: no one can sign in. Sign-in still lives in the web app (Auth.js), which the server only trusts through a JWT.

Goal: the server runs the whole Google sign-in itself — OAuth 2.0 Authorization Code with PKCE plus OpenID Connect — signs a user up on their first sign-in (user + personal workspace), links a returning user by `(provider, subject)` or by verified email, then issues the session cookie and sends the browser back to the web app. Logout and "sign out everywhere" routes revoke sessions and clear the cookie. No auth SDK: `httpx` + `PyJWT` only.

## User stories

1. As a visitor, I want a "Sign in with Google" link that sends me to Google, so that I can sign in without a Metis password.
2. As a visitor, I want the web app to ask the server which sign-in providers exist (`GET /v1/auth/providers`), so that it only shows buttons that work.
3. As a new user, I want my first Google sign-in to create my account and my personal workspace, so that I can start using Metis right away.
4. As a returning user, I want my next sign-in to land in the same account and workspace, so that my ideas are still there.
5. As a user who signed up through the old Auth.js flow, I want my first server-side Google sign-in to find my existing account, so that I don't end up with two accounts.
6. As a user whose Metis account has the same verified email as my Google account, I want the Google identity linked to that account, so that I never get a duplicate.
7. As a user, I want to be sent back to the page I started from (`redirect_to`), so that sign-in doesn't lose my place.
8. As a user, I want a sign-in failure to bring me to the web sign-in page with an error code, so that I see a clear message instead of a JSON error.
9. As a user, I want to be signed in by an `HttpOnly` session cookie after the callback, so that page scripts can't read my credentials.
10. As a user, I want "Sign out" to end this session and clear the cookie, so that the next request is anonymous.
11. As a user, I want "Sign out everywhere" to end every one of my sessions, so that a lost device is cut off.
12. As a user whose Google email is not verified, I want sign-in refused (`auth.email_unverified`), so that nobody can claim an account with an email they don't own.
13. As a user, I want a sign-in link that was already used, expired (10 min) or never issued to be refused (`auth.oauth_state_invalid`), so that a replayed or forged callback can't sign anyone in.
14. As a user, I want a forged or tampered `id_token` (bad signature, wrong issuer, wrong audience, expired, wrong nonce) refused, so that only Google can vouch for who I am.
15. As a user, I want a `redirect_to` that points off-site to fall back to `/`, so that sign-in links can't be abused to send me to a phishing page.
16. As a user who cancels on Google's consent screen, I want to land back on the sign-in page with an error code, so that I can try again.
17. As an operator, I want the authorization code flow to use PKCE (`S256`), a random `state` and a random `nonce`, so that stolen codes and CSRF on the callback are useless.
18. As an operator, I want the OAuth `state`, `nonce`, `code_verifier` and `redirect_to` kept server-side in Redis for 10 minutes and deleted on first read, so that each login attempt can be finished exactly once.
19. As an operator, I want Google's discovery document and JWKS fetched over HTTPS and cached, with a JWKS refetch when a `kid` is unknown, so that Google key rotation works without a restart.
20. As an operator, I want Google failures (network, non-2xx token response, malformed JSON) mapped to `auth.oauth_failed` and logged with a reason, so that I can debug outages without leaking secrets.
21. As an operator, I want `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (SecretStr) and `GOOGLE_REDIRECT_URI` in config, so that each environment uses its own OAuth client.
22. As an operator, I want the authorization code, `code_verifier`, tokens, `id_token` and client secret never logged, so that logs can't be used to sign in.
23. As an operator, I want each successful sign-in to update `last_login_at` on the auth identity, so that I can see when a user last signed in.
24. As an operator, I want sign-in events logged (`auth.sign_in` with `outcome` ∈ `created`, `existing`, `linked`, and `user_id`), so that I can see sign-up and linking activity.
25. As a future email-sign-in developer, I want an `AuthProvider` protocol with `authorization_url` and `complete`, so that adding a provider doesn't touch the routes' shape or `sign_in`.
26. As the web app (SHIP-221), I want stable routes and error codes, so that I can build the sign-in page against them.
27. As a maintainer, I want HTTP-seam tests with Google mocked by a local JWKS, so that the whole flow is covered in CI without calling Google.

## Requirements

1. **`modules/identity/providers/base.py`** (new):
   - `ProviderProfile` (frozen): `provider: AuthProviderName`, `subject: str`, `email: str`, `email_verified: bool`, `name: str | None`, `avatar_url: str | None`.
   - `AuthProvider` protocol: `name`, `authorization_url(state, nonce, code_challenge) -> str` and `async complete(code, code_verifier, nonce) -> ProviderProfile`.
   - `AuthProviderName` StrEnum (`google`, `email`) matching the `auth_identities.provider` CHECK. Only `google` has an implementation.
   - PKCE helpers (`new_code_verifier()`, `code_challenge(verifier)` → S256, base64url without padding) and random `state` / `nonce` (`secrets.token_urlsafe(32)`). Put them in `core/security.py` beside the session token helpers if they are generic, else in `providers/base.py`.
2. **`modules/identity/providers/google.py`** (new):
   - Discovery document `https://accounts.google.com/.well-known/openid-configuration` (named constant), fetched with `httpx` and cached in process; `authorization_endpoint`, `token_endpoint`, `jwks_uri` and `issuer` come from it.
   - `authorization_url`: `response_type=code`, `client_id`, `redirect_uri=GOOGLE_REDIRECT_URI`, `scope=openid email profile`, `state`, `nonce`, `code_challenge`, `code_challenge_method=S256`, `prompt=select_account`.
   - `complete`: POST the code exchange (`grant_type=authorization_code`, `code`, `code_verifier`, `client_id`, `client_secret`, `redirect_uri`) to the token endpoint, then verify `id_token` with PyJWT (`PyJWKClient`-style key lookup against the JWKS, or a small cached JWKS fetched through the same `httpx` client): algorithm `RS256` only; check signature, `iss` ∈ {`https://accounts.google.com`, `accounts.google.com`}, `aud == GOOGLE_CLIENT_ID`, `exp` (small leeway, named constant), and `nonce` equal to the stored one. Map claims `sub`, `email`, `email_verified`, `name`, `picture` to `ProviderProfile`.
   - JWKS cached in process; an unknown `kid` triggers one refetch before failing.
   - The `httpx` client comes from an injectable factory (FastAPI dependency, like `provider_http_factory` in `helpers/http.py`) so tests swap in `httpx.MockTransport`. Calls are capped with the existing total-timeout helper.
   - Any network error, non-2xx, malformed body or failed `id_token` check raises `OAuthFailedError`, logged with a `reason` (never with tokens or the code).
3. **`auth_service.sign_in(session, profile) -> SignedInUser`** (extends `modules/identity/auth_service.py`; takes the caller's session, never commits):
   1. `profile.email_verified` is false → `EmailUnverifiedError`.
   2. Find the `auth_identities` row by `(provider, subject)` → that user (`outcome=existing`).
   3. Else find the user with the same email (`users.email`) → insert an `auth_identities` row for it (`outcome=linked`).
   4. Else create the user (`auth_sub = profile.subject` while that column exists; `name`, `image = avatar_url`) plus its personal workspace through the existing `service.ensure_personal_workspace`, and insert the identity (`outcome=created`).
   5. Set `auth_identities.last_login_at = now` and refresh its `email` / `email_verified`.
   6. Return the user (with personal workspace) and the outcome.
   - Concurrent first sign-ins for the same subject must not create two users: rely on `unique(provider, subject)` / `users.email` / `users.auth_sub` and retry the lookup once on conflict (savepoint, same pattern as `repo.upsert_user`).
   - New repo functions live in `sessions_repo.py`'s sibling or `repo.py` (identity-only): `get_identity`, `insert_identity`, `touch_identity`.
4. **`modules/identity/auth_api.py`** (new router, mounted under `/v1/auth`):
   - `GET /v1/auth/providers` → `200 ["google"]` (public).
   - `GET /v1/auth/google/login?redirect_to=` (public): sanitize `redirect_to`, create `state`, `nonce`, `code_verifier`, store `{nonce, code_verifier, redirect_to}` as JSON in Redis `auth:oauth:{state}` with a 600 s TTL (named constant), then `302` to the Google authorization URL.
   - `GET /v1/auth/google/callback?code=&state=` (public): atomically read-and-delete `auth:oauth:{state}` (`GETDEL`); missing → `auth.oauth_state_invalid`. A Google `error=` parameter (e.g. `access_denied`) → `auth.oauth_failed`. Then `provider.complete` → `auth_service.sign_in` → `auth_service.create_session` (user agent + client IP) → commit → `security.set_session_cookie` → `302` to `WEB_BASE_URL + redirect_to`.
   - Every callback failure (`MetisError` with codes below) responds `302` to `{WEB_BASE_URL}/sign-in?error=<code>` and sets no cookie; nothing is committed.
   - `POST /v1/auth/logout` → revoke the current cookie's session (`auth_service.logout`), clear the cookie, `204`.
   - `POST /v1/auth/logout-all` → `auth_service.logout_all` for the current user, clear the cookie, `204`.
   - Handlers stay thin: Redis state handling and provider selection live in a small service function (e.g. `auth_service.start_login` / `finish_login`), not in the router.
5. **`redirect_to` rule** (a pure helper): accept only a relative path that starts with a single `/`, is not `//…` or `/\…`, contains no scheme, host, backslash or control characters, and is at most a named max length. Anything else (including missing) → `/`. Applied at login; the stored value is reused at callback.
6. **Config** (`core/config.py`, `.env.example`, compose): `GOOGLE_CLIENT_ID` (str), `GOOGLE_CLIENT_SECRET` (`SecretStr`, redacted in settings dumps), `GOOGLE_REDIRECT_URI` (str). All three required outside development; optional in development, where Google is then not offered (see Open questions, 1).
7. **Errors** (`core/errors.py`, catalog + classes): `OAuthStateInvalidError` → `auth.oauth_state_invalid` 400, `OAuthFailedError` → `auth.oauth_failed` 502, `EmailUnverifiedError` → `auth.email_unverified` 403.
8. **Dependencies**: move `httpx` from the dev group to runtime dependencies (it is already used at runtime by `helpers/http.py`). No new auth SDK; PyJWT gets the `crypto` extra if needed for RS256 (`cryptography` is already a dependency).
9. **Logging**: `auth.sign_in` (`outcome`, `user_id`, `provider`) at `info`; `auth.oauth_failed` with `reason` at `warning`. Never log `code`, `code_verifier`, `state` value, `nonce`, tokens, `id_token` or the client secret.
10. **Docs sync**:
    - `server-context.md`: `/v1/auth/*` endpoints, the `auth:oauth:{state}` Redis key, the new error codes, Google config, the `AuthProvider` protocol.
    - `architecture.md`: Auth row — the server now runs Google sign-in; Auth.js and JWT stay until SHIP-221 / SHIP-267.
    - `.env.example`.

## Out of scope

- Web sign-in page, app shell and removing Auth.js (SHIP-221, SHIP-219).
- Switching existing routes from JWT to the session, renaming `session_user` to `current_user`, deleting `core/auth.py`, dropping `users.auth_sub` (SHIP-267).
- Email sign-in / magic links (only the enum value and the protocol shape exist).
- Unlinking identities, account merging beyond email match, a "your devices" UI.
- Refresh tokens or calling Google APIs after sign-in (only `id_token` claims are used; access/refresh tokens are discarded).
- Updating the user's `name` / `image` on later sign-ins.
- Rate limiting login/callback, session rotation of an existing cookie at sign-in, cleanup of expired session rows.

## Touches

- `server/metis/modules/identity/`:
  - New: `providers/__init__.py`, `providers/base.py`, `providers/google.py`, `auth_api.py`
  - Changed: `auth_service.py` (`sign_in`, login start/finish), `repo.py` or `sessions_repo.py` (identity rows), `models.py` / `schemas.py` (profile, sign-in DTOs), `__init__.py` (router export)
- `server/metis/core/config.py`, `server/metis/core/errors.py`, `server/metis/core/security.py` (PKCE/state helpers if generic), `server/metis/entrypoints/api.py` (mount router)
- `server/pyproject.toml` + `uv.lock` (httpx to runtime; via `uv`)
- `server/tests/modules/identity/test_auth_google_api.py` (new), `server/tests/modules/identity/conftest.py` / `api_helpers.py` (fake Google fixture), `server/tests/core/test_config.py`
- `.env.example`, `compose.yaml` (env passthrough), `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`

## Dependencies

- `feat-auth-sessions` (SHIP-264): done.
- Blocks: SHIP-221 (12.1 web sign-in through the server), SHIP-219 (12 web sign-in, shell, settings).

## Test seam

One seam, the same as SHIP-216/217/264: **HTTP requests against the FastAPI app** (`httpx.AsyncClient` + `ASGITransport`), real Postgres as `metis_app`, real Redis on `TEST_REDIS_URL`.

**Fake Google**: the Google HTTP client factory is overridden with an `httpx.MockTransport` that serves the discovery document, a token endpoint and a JWKS built from an RSA key generated in the test. The token endpoint returns an `id_token` signed by that key with claims the test chooses (and a second "attacker" key for the bad-signature case). Tests drive the real flow: call `/login`, read `state` from the `Location` header (and `nonce` / PKCE from what the fake token endpoint receives), then call `/callback`.

Planned tests:

- `/providers` → `["google"]`.
- `/login` → 302 to Google with `state`, `nonce`, `code_challenge`, `code_challenge_method=S256`, `scope=openid email profile`; Redis holds `auth:oauth:{state}` with TTL ≤ 600 s.
- First callback → user + personal workspace + `google` identity created; `Set-Cookie` session cookie; 302 to `WEB_BASE_URL + redirect_to`; `GET /v1/me` (or the session probe) with the cookie resolves that user.
- Second sign-in, same subject → same user, no new workspace; `last_login_at` advanced.
- Existing user with the same email and a different/no identity → identity linked, no duplicate user.
- Backfilled Auth.js user (identity from `auth_sub`) → found by subject.
- `email_verified=false` → 302 `…/sign-in?error=auth.email_unverified`, no user, no cookie.
- Reused `state` (second callback), unknown `state`, expired `state` (key deleted/TTL elapsed) → `error=auth.oauth_state_invalid`.
- Tampered `id_token`: bad signature, wrong `aud`, wrong `iss`, expired, wrong `nonce` → `error=auth.oauth_failed`; token endpoint 400/500 or network error → `auth.oauth_failed`; Google `error=access_denied` → `auth.oauth_failed`.
- The token exchange sends the `code_verifier` matching the `code_challenge` from `/login`.
- `redirect_to`: `https://evil.example`, `//evil.example`, `/\evil.example`, `javascript:…`, missing → `/`; `/ideas/123?tab=x` kept.
- Logout → 204, cookie cleared, the next `/v1/_test/session` request → 401. Logout without a cookie → 204. Logout or logout-all without `X-Metis-Client: web` → 403 `auth.csrf_failed`. Logout-all without a session → 401. Logout-all → every session of the user 401, another user's session still 200.
- Logs across a full sign-in contain no code, verifier, `id_token` or client secret.
- Config: `GOOGLE_CLIENT_SECRET` is a `SecretStr` and is redacted.
- Pure tests for the `redirect_to` sanitizer and the PKCE `code_challenge` (RFC 7636 test vector).

## Acceptance criteria

- [x] With Google mocked by a local JWKS: first sign-in creates user + workspace; the second reuses them; a matching verified email links instead of duplicating.
- [x] Reused, expired or unknown `state` is rejected; a tampered `id_token` (bad signature, wrong `aud`, wrong `nonce`) is rejected.
- [x] `redirect_to=https://evil.example` falls back to `/`.
- [x] Logout makes the next session-authenticated request (`/v1/_test/session`) return 401; logout-all signs out every session. (`/v1/me` moves to sessions in SHIP-267.)
- [x] Unverified Google email is refused with `auth.email_unverified`.
- [x] Callback errors redirect to `{WEB_BASE_URL}/sign-in?error=<code>` and set no cookie.
- [x] `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (SecretStr), `GOOGLE_REDIRECT_URI` are in `Settings` and `.env.example`.
- [x] No auth SDK added; `httpx` is a runtime dependency.
- [x] `server-context.md` and `architecture.md` describe the flow, routes, Redis key and errors.
- [x] `uv run ruff check`, `uv run mypy` and `uv run pytest` pass.

## Open questions

None. Resolved 2026-11-14 (see Decisions in `progress-tracker.md`):

1. **Google config presence**: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `GOOGLE_REDIRECT_URI` are **required outside development** (settings validation fails when any is missing and `ENV` is not development). In development they may be unset: `/v1/auth/providers` then returns `[]` and `/google/login` redirects to `/sign-in?error=auth.oauth_failed`. Tests set them. Add a config test for both cases.
2. **Logout rules**: both logout routes follow the SHIP-264 CSRF rule (`X-Metis-Client: web` required). `logout` is idempotent: a missing or unknown cookie still gets 204 and a cleared cookie. `logout-all` needs a valid session (`SessionUserDep`, 401 otherwise).
3. **Logout check**: the acceptance test asserts 401 on the SHIP-264 session probe route (`/v1/_test/session`). `/v1/me` stays on JWT until SHIP-267.
4. **Test seam**: one HTTP seam with Google faked by `httpx.MockTransport` and a test-generated RSA JWKS, plus two pure-function tests (`redirect_to`, PKCE). Confirmed.

Defaults taken without asking (from the issue or existing patterns):
- New users get `users.auth_sub = Google subject` while the column exists (it is NOT NULL UNIQUE until SHIP-267).
- Email linking matches `users.email` exactly as Google returns it (Google emails are lowercase).
- A Google `error=` on the callback maps to `auth.oauth_failed` (no new code).
- Redis unavailable at login or callback fails the attempt with `auth.oauth_failed` (state can't be stored or proved).
- The plan file `plans/server-auth-google.md` named in the issue's Agent notes is not in the repo; this PRD relies on the issue text.

## Review follow-ups (2026-11-14)

Two-axis review (standards + spec). Fixed:

- **Query strings in access logs:** `uvicorn.access` logged the full request line, so the callback's `code` and `state` would have reached the logs. `core/logging.py` now installs `StripQueryFilter` on that logger (tests in `tests/core/test_logging.py`).
- **Orphan rows:** each `sign_in` attempt runs in its own savepoint, and `finish_login` wraps `sign_in` + `create_session` in one. A lost race or a later failure leaves no user, workspace or identity behind. A test fails `create_session` and asserts nothing was stored. The route no longer calls `session.rollback()`.
- `oauth_failed` takes `OAuthStep` and `OAuthFailure` enums, not strings. Upstream reasons map to `rejected`, `unreachable`, `timeout` or `bad_response`.
- Duplicated code: `repo.insert_or_none` (savepoint insert) is shared by `insert_user` and `insert_identity`. Google response parsing goes through one `_parse` helper.
- `identities_repo` takes `AuthProviderName`. `email_verified` comes from the profile, not a literal. The test imports the state TTL and key prefix. Status codes and `S256` / `select_account` are named constants.
- Docs: `server-context.md` no longer claims `core/auth.py` is the only PyJWT import. `architecture.md` records why providers live in `modules/identity/providers/`, not `adapters/`.

Deviations from the requirements above, kept on purpose:

- `AuthProvider.authorization_url` is `async`, because it needs Google's discovery document.
- The provider repo is `identities_repo.py`, and `touch_identity` is called `record_login`.
- The HTTP client factory is injected into `GoogleProvider` (built once in `get_google_provider`), and tests override `get_google_provider`. It is not a per-request FastAPI dependency, because the provider's discovery and JWKS caches must outlive a request.
- `sign_in` also finds a user by `users.auth_sub = Google subject` before email. This covers Auth.js users created after the `0006` backfill whose email has changed. It goes away with `auth_sub` in SHIP-267.
- An unknown `kid` refetches the JWKS at most once a minute. Discovery and JWKS are cached for 1 h.
- `compose.yaml` is unchanged: every service already reads `.env`.

Not changed:

- **Commit failure on the callback:** this is a 500, not a `/sign-in?error=` redirect. The commit runs when `SessionDep` exits, after the handler returns, and no cookie is sent. Routes don't commit (`code-standards.md`).
- **`_google_from_settings`** checks the three fields itself instead of using `settings.google_configured`, so that mypy can narrow the `None`s.
- **No controller-only tests with a mocked service:** the agreed seam is HTTP (Decisions, 2026-11-14).
- **Migration formatting:** `ruff format --check` flags existing migration files. They are protected and were already unformatted on the base branch, so they are untouched.

## Status

done
