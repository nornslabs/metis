# Server Context

## Runtime Model

One Python codebase (`server/metis`), one Docker image, three logical processes (the worker runs as one container per queue). API records intent and streams; workers do all agent work; scheduler only enqueues.

| Process     | Entrypoint                 | Job                                                |
| ----------- | -------------------------- | -------------------------------------------------- |
| `api`       | `entrypoints/api.py`       | FastAPI REST `/v1`, SSE, auth                      |
| `worker`    | `entrypoints/worker.py`    | Arq jobs: `run_graph`, `market_scan`, outbox relay; one process per queue (`AgentWorkerSettings`, `MaintenanceWorkerSettings`) |
| `scheduler` | `entrypoints/scheduler.py` | Market-watch ticks (15 min), nightly jobs          |

## Configuration

All config via env, loaded into `core/config.py` (pydantic-settings). No hardcoded values.

| Purpose          | Env var                                                   |
| ---------------- | --------------------------------------------------------- |
| Postgres         | `DATABASE_URL`                                            |
| Redis            | `REDIS_URL`                                               |
| Sessions         | `SESSION_COOKIE_NAME` (default `metis_session`), `SESSION_TTL_DAYS` (30), `SESSION_IDLE_DAYS` (7; `1 ≤ idle ≤ ttl`), `COOKIE_DOMAIN` (optional), `COOKIE_SECURE` (optional; unset ⇒ `Secure` unless `APP_ENV=development`, read as `settings.secure_cookies`) |
| Google sign-in   | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (SecretStr), `GOOGLE_REDIRECT_URI`; all required unless `APP_ENV=development`, where unset ⇒ Google not offered (`settings.google_configured`) |
| Web app URL      | `WEB_BASE_URL` (default `http://localhost:3000`; sign-in redirects) |
| Key encryption   | `ENCRYPTION_MASTER_KEY`                                   |
| Web origin       | `CORS_ORIGINS` (comma-separated, e.g. `http://localhost:3000,http://localhost:8000`) |
| App DB role      | `APP_DB_PASSWORD` (read by migration `0004_app_role` only; gives `metis_app` LOGIN) |
| Tracing          | `LANGFUSE_*`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `SENTRY_DSN` |

LLM and Exa keys are not env vars: they are per workspace (BYO), stored encrypted in `identity.provider_keys` (see Modules). `APP_ENV=development` is the only setting that allows an `http://localhost` (or `127.0.0.1`, `::1`) LLM `base_url`; everywhere else `base_url` must be https.

Secrets (`core/crypto.py`): envelope encryption with AES-256-GCM. `encrypt(plaintext, workspace_id) -> SealedSecret{ciphertext, nonce, wrapped_key, key_version}` seals each secret with its own random data key, wrapped by the master key for `key_version` (today only `1` = `ENCRYPTION_MASTER_KEY`). `workspace_id` is the AAD of both layers, so a secret cannot be opened in another workspace. `decrypt(sealed, workspace_id)` raises `SecretDecryptError` (`crypto.decrypt_failed`, 422: re-enter the key) on a wrong workspace, tampering or an unknown version. `mask(secret)` shows first 3 + `…` + last 4 for secrets of 12+ chars, else `…••••`. Never log or return plaintext.

## Ports

Core interfaces in `core/ports.py`. Adapters implement them; nothing else imports a vendor SDK.

| Port             | MVP adapter                                  | Used by                     |
| ---------------- | -------------------------------------------- | --------------------------- |
| `LLMProvider`    | OpenAI-compatible (`ChatOpenAI`, `base_url`) | agent graph                 |
| `ResearchSource` | Exa hosted MCP server (`mcp.exa.ai/mcp`)     | Researcher, Scorer, Advisor |
| `OutputSink`     | Linear MCP, Markdown                         | Integrator                  |
| `InputChannel`   | Web (REST + SSE)                             | API                         |

Vendor adapters live in `metis/adapters/` and build on the shared plumbing in `metis/helpers/` (`httpx` and the `mcp` SDK; no vendor SDK):

- `helpers/http.py`: `provider_http_factory` (FastAPI dependency returning a `ClientFactory`: `make_client(headers) -> httpx.AsyncClient`, per-phase timeout, no redirects; adapters open one short-lived client per call; tests override it to route to fakes), `capped(provider)` (caps a whole call at `PROVIDER_TIMEOUT_SECONDS` = 10 s, else `timeout`) and `send(http, provider, request)`, which returns the JSON body or raises `UpstreamError` with `meta = {provider, reason}`, reason one of `unauthorized` (401/403), `unreachable`, `timeout`, `bad_response`. Keys, headers and upstream bodies never reach the error or logs.
- `adapters/llm.py`: `OpenAICompatibleClient(make_client, base_url, api_key, model)` preserves `list_models()` (`GET {base_url}/models`, spends no tokens) and implements the `LLMProvider` port with async chat calls and tool binding. Calls use the shared 10 s cap, no SDK retries, and safe `UpstreamError` mapping. Returned `AIMessage` usage metadata is available to run accounting.
- `agent/llm.py`: `llm_provider(session, workspace_id, make_client)` loads credentials only through `identity.get_key_for_use`, yields a provider for that workspace, and closes its HTTP client when the run scope ends. Do not log or return the decrypted credentials.
- `helpers/mcp.py`: `open_mcp_session(http, url, provider)` connects to a remote MCP server over streamable HTTP with a caller-built client (auth headers on the client), runs the handshake and yields a `ClientSession`; any failure becomes `UpstreamError` (`unauthorized` for HTTP 401/403, `timeout`, `unreachable`, else `bad_response`). Shared by every MCP-backed provider.
- `adapters/mcp/exa.py`: `ExaMcpClient(make_client, api_key).check()` calls Exa's hosted MCP server (`https://mcp.exa.ai/mcp`, key in `x-api-key`): one `web_search_exa` call with `numResults: 1` (`query` and `objective` are required). Exa also serves keyless searches, so only a tool call proves a key; a bad key comes back as a tool `isError` with `(401)` in its text → `unauthorized`. No `exa-py`.

## Domain Primitives

| Primitive        | Values                                                                                                                 |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------- |
| IDs              | UUIDv7; every tenant row has `workspace_id`                                                                            |
| `Stage`          | `intake`, `interviewing`, `researching`, `scoring`, `advising`, `spec_draft`, `spec_confirmed`, `planning`, `exported` |
| `RunStatus`      | `queued`, `running`, `awaiting_user`, `succeeded`, `failed`, `cancelled`                                               |
| `RunEventType`   | `node_started`, `node_finished`, `token`, `tool_call`, `interrupt`, `run_status`                                       |
| `DomainEventType`| `IdeaSubmitted`, `ScoreComputed`, `SpecConfirmed`, `PlanReady`, `ExportFinished`, `MarketSignalDetected`               |
| `MemberRole`     | `owner`, `member`                                                                                                      |
| `ProviderKind`   | `llm` (OpenAI-compatible: `base_url` + key + `model`), `exa` (key only)                                                |
| `ScoreParam`     | `problem_severity` 25, `uniqueness` 25, `market_demand` 15, `value` 15, `feasibility` 10, `timing` 10                  |
| `ScoreBand`      | `build` (75+), `promising` (55–74), `advise` (<55)                                                                     |
| `ScoreTrigger`   | `manual`, `scheduled`, `signal`                                                                                        |
| `SignalKind`     | `new_competitor`, `shutdown`, `funding`, `trend`                                                                       |
| `SuggestionKind` | `feature`, `niche`, `pricing`, `pivot`                                                                                 |
| `ExportMode`     | `export`, `rebalance`                                                                                                  |
| Estimates        | Fibonacci points 1, 2, 3, 5, 8 (split above 8)                                                                         |

Immutable, versioned: score runs, spec versions, research snapshots.

## Modules

`modules/<name>/` with `controller/` (HTTP routes), `service/` (business logic), `repo/` (all Postgres access, one file per table), `cache/` (all Redis key/value caches, one file per cache, when the module has any), `models/`, `dto/` (Pydantic data-transfer objects), `helpers/` (local, module-only), `events.py`; a layer is a folder with one file per domain when it covers several (see `code-standards.md`). Only `__init__.py` is public. Each module owns one Postgres schema.

| Module          | Owns                                             |
| --------------- | ------------------------------------------------ |
| `auth`          | users, sessions, sign-in identities, OAuth       |
| `identity`      | workspaces, members, provider keys, settings     |
| `ideas`         | ideas, interview turns, specs, workflow runs     |
| `research`      | snapshots, items, competitor KB, signals         |
| `scoring`       | score runs, params, suggestions, rubric versions |
| `planning`      | HLD, phases, tasks, task deps, plan diffs        |
| `integrations`  | MCP connections, export jobs, external refs      |
| `memory`        | memories (pgvector), guidance versions           |
| `notifications` | in-app notifications                             |

Import rules (import-linter, contracts in `server/pyproject.toml`, checked by `uv run lint-imports` in CI): `metis.core` and `metis.helpers` import nothing from `metis.modules`; `metis.modules.auth` imports no other module; `identity` sits above `auth` in a layers contract, so `identity → auth` is allowed and `auth → identity` fails. Identity imports only `metis.modules.auth` (its public surface: `router`, `current_user`, `CurrentUserDep`, `check_csrf`, `SessionUser`, `User`, `get_user`, `find_user_by_email`), never auth's `controller`, `service`, `models`, `repo`, `cache` or `dto`; a fourth import-linter contract ("identity uses only auth's public surface") fails CI on a direct import of any of them. `core/db.py` `insert_or_none(session, stmt)` (runs an `INSERT … RETURNING` in a savepoint, `None` on a unique conflict) is shared by both modules' `repo/` files.

Identity service contract (`modules/identity/service/`: `workspaces.py`, `members.py`, `provider_keys.py`, `settings.py`; the public functions are re-exported by `metis.modules.identity`): `ensure_personal_workspace(session, user)` (one `is_personal` workspace per user, race-safe), `list_workspaces(session, user)`, `create_workspace(session, user, name)`, `add_member(session, actor, workspace_id, email, role)` (owner only, else `PermissionDeniedError`; looks the email up with `auth.find_user_by_email`, unknown → `MemberUserNotFoundError`; existing member `AlreadyMemberError`). Every function takes the caller's `AsyncSession`, never commits (the caller owns the transaction) and sets its own RLS context (`app.user_id` / `app.workspace_id`, transaction-local), restoring the caller's value afterwards. Invalid input raises `InvalidInputError` (422) via `helpers.validation.validate_input`.

Identity provider keys and settings (same session rules): `get_settings_overview(session, workspace_id)` → masked keys + settings; `set_key(session, membership, kind, value, base_url?, model?)` seals the key with `crypto.encrypt` (workspace id as AAD), stores `sealed` (base64 `SealedSecret` fields, JSONB) and `masked`, upserts on `(workspace_id, kind)`, bumps `version` and clears the last test result; `delete_key(session, membership, kind)` (none → `ProviderKeyNotFoundError` 404); `test_key(session, workspace_id, kind, make_client)` makes one adapter call and records `last_tested_at`/`last_test_ok`, returning a `KeyTestResult` whose `error` is the `UpstreamError` (not raised, so the result commits); `get_key_for_use(session, workspace_id, kind)` → `ProviderCredentials{kind, api_key, base_url, model}` (none → `ProviderNotConfiguredError`), callable only by the LLM gateway and the Exa adapter; `update_settings(session, membership, patch)` with optimistic concurrency (`version` 0 = never saved: creates the row; stale → `ConflictError` 409). Writes (`set_key`, `delete_key`, `update_settings`) are owners only (`PermissionDeniedError` 403); any member reads and tests. Settings: `run_budget_usd` default 2.00, `0 < x ≤ 100`, 2 decimals; `max_steps` default 50, `1 ≤ x ≤ 200`; no row means defaults (`version` 0). Both tables have RLS.

Identity routes (`modules/identity/controller/`: `workspaces.py`, `settings.py`): `GET /v1/workspaces/current` → `{workspace, role}` (the request's current workspace, `X-Workspace-Id` or the personal one; the first call creates the personal workspace); `GET /v1/workspaces` → `{items: [{workspace, role}], next_cursor: null}`; `POST /v1/workspaces` `{name}` → `201 {workspace, role: "owner"}`; `GET /v1/settings` → `{keys: {llm, exa}, settings: {run_budget_usd, max_steps, version}}` (a key is `{kind, base_url, model, masked, last_tested_at, last_test_ok, version, updated_at}` or `null`); `PATCH /v1/settings` `{version, run_budget_usd?, max_steps?}` → settings or 409; `PUT /v1/settings/keys/{kind}` `{value, base_url?, model?}` → key; `DELETE /v1/settings/keys/{kind}` → 204; `POST /v1/settings/keys/{kind}/test` → key (ok) or 502 `provider.upstream_error` with `meta {provider, reason}`. No response ever contains a plaintext key.

## Auth and Request Scope

- Auth is the session cookie only (SHIP-267 removed JWT bearer auth, `core/auth.py` and `AUTH_JWT_*`). An `Authorization` header is ignored. PyJWT is imported only by `modules/auth/providers/google.py` (Google `id_token`s).
- `core/db.py`: `SessionDep` = one `AsyncSession` per request (`get_request_session`, `scope="function"`), shared by every dependency and the route; committed before the response is sent, rolled back on any exception. `set_workspace(session, id)` / `set_user(session, id)` set `app.workspace_id` / `app.user_id` for the transaction.
- `modules/auth/deps.py` (exported from `metis.modules.auth`): `current_user` (`CurrentUserDep`) → `SessionUser{user, session_id}` (frozen, in `auth/dto/sessions.py`). Checks in order: no cookie → `NotSignedInError` (`auth.not_signed_in`, 401); `POST`/`PUT`/`PATCH`/`DELETE` without `X-Metis-Client: web` → `CsrfError` (`auth.csrf_failed`, 403); then the session must resolve (`auth.session_expired`, 401). Binds `user_id` and `session_id` to logs. 401s carry no `WWW-Authenticate` header.
- `modules/identity/deps.py` (exported from `metis.modules.identity`): `current_workspace` (`CurrentWorkspaceDep`, built on `auth.CurrentUserDep`) reads `X-Workspace-Id` (absent → personal workspace, created by `ensure_personal_workspace` if missing; not a UUID → 422; not a member or unknown → `PermissionDeniedError` 403, same error for both), then sets `app.user_id` and `app.workspace_id` on the request session and binds `workspace_id`/`user_id` to logs. Returns the caller's `Membership`.
- Every `/v1` route except `/v1/health` and the public `/v1/auth/*` routes (`providers`, `google/login`, `google/callback`, `logout`) depends on `current_user` or `current_workspace`; tenant routes use `current_workspace` so RLS is scoped. `tests/modules/auth/test_route_auth.py` walks the route table and fails on any other route that answers without a session.
- **Server sessions (SHIP-264):**
  - `core/security.py`: `new_session_token()` (32 random bytes, URL-safe), `hash_session_token(token)` (SHA-256 digest; only the hash is stored), `set_session_cookie(response, token)` / `clear_session_cookie(response)` (`SESSION_COOKIE_NAME`, `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` = `settings.secure_cookies`, `Domain` = `COOKIE_DOMAIN` when set, `Max-Age` = `SESSION_TTL_DAYS`).
  - `core/redis.py`: one process-wide Redis client (`get_redis` / `RedisDep`, 0.5 s socket timeouts), closed in the API lifespan.
  - Tables `auth.users`, `auth.identities` (`user_id`, `provider` ∈ `google`, `email`, `subject`, `email`, `email_verified`, `last_login_at`; unique `(provider, subject)`) and `auth.sessions` (`token_hash` unique, `last_seen_at`, `expires_at`, `revoked_at`, `user_agent`, `ip inet`); sessions and identities cascade on user delete. No RLS; only the auth module reads them. `identity.workspaces.created_by` and `identity.members.user_id` reference `auth.users`. `0006_auth_sessions` backfilled one `google` identity per existing user from `users.auth_sub`; `0007_drop_users_auth_sub` dropped that column; `0008_auth_schema` moved all three tables from `identity` to `auth` (`SET SCHEMA`, no data copied). `0009_rename_auth_identities` renamed `auth.auth_identities` to `auth.identities` (with its `pk_`/`fk_`/`uq_`/`ck_` constraints and `ix_identities_user_id`); model `IdentityRow`.
  - `modules/auth/service/` (`sessions.py`, `users.py`, `identities.py`, `oauth.py`, called domain-qualified, e.g. `service.sessions.create_session`; caller's session, never commits): `create_session(session, user_id, user_agent, ip) -> NewSession{token, session_id, expires_at}`; `resolve_session(session, redis, token) -> ActiveSession` (unknown, revoked, `now ≥ expires_at` or idle `≥ SESSION_IDLE_DAYS` → `SessionExpiredError`; writes `last_seen_at` at most every 5 min); `logout(session, redis, token)` (no-op if unknown); `logout_all(session, redis, user_id) -> count`; `get_session_user(session, active) -> SessionUser`; `get_user(session, user_id) -> User | None` and `find_user_by_email(session, email) -> User | None` (email trimmed, case-insensitive, as `add_member` does). Only `get_user` and `find_user_by_email` are exported; the rest is internal to auth (its routes, `deps.py` and tests).
  - Session cache (`modules/auth/cache/sessions.py`: `read`, `write`, `mark_revoked`): Redis `auth:session:{hex hash}` → `SessionRecord` JSON, TTL `min(60 s, until expires_at)`, active sessions only. Revoking writes a tombstone `auth:session:revoked:{hex hash}` (120 s, longer than any entry) and deletes the entry; readers check the tombstone first, so a request that read the session before the revocation committed cannot re-cache it, and revocation applies on the next request. A rolled-back logout leaves the session refused until the tombstone expires. If Redis is down at logout, a cached entry stays valid for up to 60 s (`auth.session_cache_evict_failed`). Other Redis errors are logged (`auth.session_cache_unavailable`) and fall back to Postgres.
  - Never log the raw token, `Cookie` or `Set-Cookie`. Rejections log `auth.session_rejected` with `reason` ∈ `missing`, `unknown`, `expired`, `idle`, `revoked`, `csrf` (plus `session_id` when known).
- **Google sign-in (SHIP-265):**
  - Providers (`modules/auth/providers/`): `AuthProvider` protocol (`name`, `async authorization_url(state, nonce, code_challenge)`, `async complete(code, code_verifier, nonce) -> ProviderProfile{provider, subject, email, email_verified, name, avatar_url}`), `AuthProviderName` (`google`, `email`; matches the `auth.identities.provider` CHECK). `GoogleProvider` uses only `httpx` + PyJWT: discovery document and JWKS cached 1 h per instance; an unknown `kid` refetches the JWKS at most once a minute; `id_token` checked `RS256` only, signature, `iss` ∈ {`https://accounts.google.com`, `accounts.google.com`}, `aud = GOOGLE_CLIENT_ID`, `exp`/`iat`/`sub` required (30 s leeway), then `nonce` (constant-time). Scopes `openid email profile`, `prompt=select_account`. `get_google_provider` / `GoogleProviderDep` → one process-wide instance or `None` when not configured (tests override it). Every failure is `OAuthFailedError`, logged `auth.oauth_failed` with `provider`, `step` (`OAuthStep`) and `reason` (`OAuthFailure`).
  - `core/security.py`: `new_oauth_value()` (state / nonce, 32 random bytes), `new_code_verifier()`, `code_challenge(verifier)` (PKCE `S256`). `helpers/redirects.py`: `safe_relative_path(value)` keeps only a same-site relative path (starts with one `/`, no scheme/host, no backslash or control characters, ≤ 2048 chars), else `/`.
  - `auth.service.identities.sign_in(session, profile) -> SignedIn{user, outcome}`: unverified email → `EmailUnverifiedError` (always, even for a known identity); `(provider, subject)` match → `existing`; else a user with the same email gets the identity linked → `linked`; else a new user → `created` (no personal workspace; see `current_workspace`). A malformed profile (bad email, non-HTTP image, overlong name) → `auth.oauth_failed`. Sets `last_login_at` and refreshes the identity's email. A unique-constraint race retries once (savepoints), then `auth.oauth_failed` (`sign_in_conflict`). Logs `auth.sign_in` (`provider`, `outcome`, `user_id`).
  - OAuth round trip (`modules/auth/service/oauth.py`): `start_login(redis, provider, redirect_to)` stores `PendingLogin{nonce, code_verifier, redirect_to}` at Redis `auth:oauth:{state}` (600 s, `cache/oauth.py` `save_pending`) and returns the provider URL; `finish_login(...)` takes it back with `GETDEL` (`take_pending`; single use; missing/unknown/expired/corrupt → `OAuthStateInvalidError`), then provider `error=` / missing code → `auth.oauth_failed`, `provider.complete`, `sign_in`, `create_session`. Redis down at login or callback → `auth.oauth_failed`.
  - Routes (`modules/auth/controller/`: `providers.py`, `google.py`, `sessions.py`; `/v1/auth`, public): `GET /providers` → `["google"]` (or `[]`); `GET /me` → the signed-in `User` (session cookie required; touches no workspace); `GET /google/login?redirect_to=` → 302 to Google; `GET /google/callback` → commit, set the session cookie, 302 to `WEB_BASE_URL + redirect_to`; any failure → rollback, no cookie, 302 to `{WEB_BASE_URL}/sign-in?error=<code>`. `POST /logout` → CSRF check (`check_csrf`), revoke the cookie's session if any, clear the cookie, 204 (idempotent). `POST /logout-all` → `CurrentUserDep` (401 without a session), revoke all the user's sessions, clear the cookie, 204.
  - Never logged: the code, `code_verifier`, `state`, `nonce`, tokens, `id_token`, the client secret. `core/logging.py` installs `StripQueryFilter` on `uvicorn.access`, so access lines carry the path without its query string (the callback's `code` and `state` live there).
  - Sign-in writes (`sign_in` + `create_session`) run in a savepoint inside `finish_login`, and each `sign_in` attempt in its own, so a failed callback or a lost race leaves no user, identity or session behind.
- CORS: only `CORS_ORIGINS` (`*` fails settings validation), credentials allowed (session cookie), headers `Content-Type`, `X-Workspace-Id`, `Idempotency-Key`, `X-Request-ID`, `X-Metis-Client`.
- DB roles: api and workers connect as `metis_app` (`NOSUPERUSER NOBYPASSRLS`, DML on `core`, `identity` and `auth` + default privileges; `auth` granted by `0008_auth_schema`); migrations run as the owner. A migration adding a schema grants `metis_app` on it.

## Agent Graph

One LangGraph `StateGraph` in `agent/graph.py`, compiled with `AsyncPostgresSaver` (`thread_id` = run id).

| Specialist  | Tools                                                                                                           |
| ----------- | --------------------------------------------------------------------------------------------------------------- |
| Supervisor  | none; routes on `MetisState.stage`                                                                              |
| Interviewer | `ask_user`, `recall_memory`, `save_interview_turn`                                                              |
| Researcher  | Exa MCP (`web_search_exa`, `web_fetch_exa`), `kb_lookup`, `kb_upsert_competitor`, `save_research_item`          |
| Scorer      | Exa MCP (`web_search_exa`), `kb_lookup`, `get_rubric`, `submit_scores`                                          |
| Advisor     | Exa MCP (`web_search_exa`), `kb_lookup`, `save_suggestion`                                                      |
| Architect   | `recall_memory`, `save_spec`, `save_hld`, Notion MCP                                                            |
| Planner     | `save_plan`, Linear MCP (read)                                                                                  |
| Integrator  | Linear MCP (write, after approval)                                                                              |

- `ask_user` and approvals call `interrupt()`; resume with `Command(resume=value)`.
- State holds ids and summaries only. Stream with `astream(stream_mode=["updates","messages","custom"])`.

## API Conventions

| Concern     | Rule                                                                            |
| ----------- | ------------------------------------------------------------------------------- |
| Prefix      | `/v1`                                                                           |
| Auth        | Session cookie (set by `/v1/auth/google/callback`); mutations also need `X-Metis-Client: web`; workspace via `X-Workspace-Id`; deps `current_user`, `current_workspace` |
| Start work  | `202 {run_id}` + `Idempotency-Key` header                                       |
| Lists       | `{items, next_cursor}`                                                          |
| Errors      | RFC 7807 `{type, title, status, detail, code}`                                  |
| Conflicts   | `version` field, `409` on mismatch                                              |
| Live events | `GET /v1/runs/{id}/events` (SSE, `Last-Event-ID`; session cookie via `EventSource` with credentials, no stream token) |

## Jobs and Events

| Queue         | Jobs                                          | Notes                    |
| ------------- | --------------------------------------------- | ------------------------ |
| `agent`       | `run_graph(run_id, resume?)`                  | one per run (Redis lock) |
| `watch`       | `run_graph` with `stage=watch`                | keyed `idea_id:date`     |
| `maintenance` | `outbox_relay`, `distill_guidance`, `cleanup` | single concurrency (`max_jobs=1`), own worker process |

Enqueue only through `core.jobs.enqueue(job_name, *args, job_id=...)`; a job must be listed in `JOB_QUEUES`. The same `job_id` enqueues once. Job functions use `@logged_job` (binds `job_id`, `run_id`, `workspace_id`). The `watch` queue lands with market-watch. Scheduler is an Arq cron worker whose jobs only enqueue (`outbox_relay` every 5 s, `cleanup` nightly 03:00 UTC).

Run events go through `core.events`: `publish(run_id, type, data)` appends to the Redis stream `run:{run_id}` (`MAXLEN ~ 5000`); `read(run_id, after_id, block_ms)` does one `XREAD` and yields `RunEvent{id, run_id, type, data, ts}`. The Redis entry id is the SSE event id (`Last-Event-ID`). Publishing a terminal `run_status` (`succeeded`, `failed`, `cancelled`) sets a 24 h TTL on the stream.

Domain events (`DomainEventType`) go through `core.outbox`: a service calls `add_event(session, DomainEvent(...))` inside its own transaction (it only inserts; the caller commits), so a rolled-back change leaves no event. Handlers subscribe with `@on_event(DomainEventType.X)` and receive the `DomainEvent`; they open their own sessions and use other modules only via `service.py`. The `outbox_relay` job runs `relay_once`: up to 100 unpublished events, oldest first, `FOR UPDATE SKIP LOCKED` so concurrent relays never share an event; success sets `published_at`, a handler error increments `attempts` and retries the whole event on the next run; after 10 attempts the event stops and `outbox.event_dead` is logged. Delivery is at least once, so handlers must be idempotent, keyed on `event.id` (UUIDv7 from `core.ids.uuid7`). `core.outbox` has no RLS (the relay reads across workspaces).

## Errors

Services raise domain errors from `core/errors.py`; API maps them to HTTP.

| Error               | HTTP |
| ------------------- | ---- |
| `AuthError` (`auth.unauthorized`, generic; Starlette 401s) | 401  |
| `NotSignedInError` (`auth.not_signed_in`) | 401 |
| `SessionExpiredError` (`auth.session_expired`) | 401 |
| `CsrfError` (`auth.csrf_failed`) | 403 |
| `OAuthStateInvalidError` (`auth.oauth_state_invalid`) | 400 |
| `OAuthFailedError` (`auth.oauth_failed`) | 502 |
| `EmailUnverifiedError` (`auth.email_unverified`) | 403 |
| `NotFound`          | 404  |
| `Forbidden`         | 403  |
| `IllegalTransition` | 409  |
| `ConflictError` (version mismatch) | 409  |
| `BudgetExceeded`    | 402  |
| `UpstreamError` (`provider.upstream_error`) | 502  |
| `ProviderNotConfiguredError` (`provider.not_configured`) | 402 |
| `ProviderKeyNotFoundError` (`provider.key_not_found`) | 404 |
| `SecretDecryptError` | 422 |
| `ValidationError`   | 422  |

## Observability

`structlog` JSON logs bound with `run_id`, `idea_id`, `workspace_id`. OpenTelemetry traces, Langfuse for LLM calls and cost, Sentry for exceptions. Never log keys, tokens or prompts containing them.
