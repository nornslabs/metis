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
| JWT verification | `AUTH_JWT_SECRET`, `AUTH_JWT_AUDIENCE`                    |
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
- `adapters/llm.py`: `OpenAICompatibleClient(make_client, base_url, api_key).list_models()` (`GET {base_url}/models`, spends no tokens). The LLM gateway (SHIP-220) extends it.
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

`modules/<name>/` with `api.py`, `service.py` (public), `models.py`, `repo.py`, `schemas.py`, `events.py`. Each owns one Postgres schema.

| Module          | Owns                                             |
| --------------- | ------------------------------------------------ |
| `identity`      | users, workspaces, provider keys, settings       |
| `ideas`         | ideas, interview turns, specs, workflow runs     |
| `research`      | snapshots, items, competitor KB, signals         |
| `scoring`       | score runs, params, suggestions, rubric versions |
| `planning`      | HLD, phases, tasks, task deps, plan diffs        |
| `integrations`  | MCP connections, export jobs, external refs      |
| `memory`        | memories (pgvector), guidance versions           |
| `notifications` | in-app notifications                             |

Identity service contract (`modules/identity/service.py`): `upsert_user_from_claims(session, sub, email, name, image)` (upsert on `users.auth_sub`, email lower-cased; email owned by another account `EmailTakenError`), `ensure_personal_workspace(session, user)` (one `is_personal` workspace per user, race-safe), `list_workspaces(session, user)`, `create_workspace(session, user, name)`, `add_member(session, actor, workspace_id, email, role)` (owner only, else `PermissionDeniedError`; unknown email `MemberUserNotFoundError`; existing member `AlreadyMemberError`). Every function takes the caller's `AsyncSession`, never commits (the caller owns the transaction) and sets its own RLS context (`app.user_id` / `app.workspace_id`, transaction-local), restoring the caller's value afterwards. Invalid input raises `InvalidInputError` (422) via `helpers.validation.validate_input`.

Identity provider keys and settings (same session rules): `get_settings_overview(session, workspace_id)` → masked keys + settings; `set_key(session, membership, kind, value, base_url?, model?)` seals the key with `crypto.encrypt` (workspace id as AAD), stores `sealed` (base64 `SealedSecret` fields, JSONB) and `masked`, upserts on `(workspace_id, kind)`, bumps `version` and clears the last test result; `delete_key(session, membership, kind)` (none → `ProviderKeyNotFoundError` 404); `test_key(session, workspace_id, kind, make_client)` makes one adapter call and records `last_tested_at`/`last_test_ok`, returning a `KeyTestResult` whose `error` is the `UpstreamError` (not raised, so the result commits); `get_key_for_use(session, workspace_id, kind)` → `ProviderCredentials{kind, api_key, base_url, model}` (none → `ProviderNotConfiguredError`), callable only by the LLM gateway and the Exa adapter; `update_settings(session, membership, patch)` with optimistic concurrency (`version` 0 = never saved: creates the row; stale → `ConflictError` 409). Writes (`set_key`, `delete_key`, `update_settings`) are owners only (`PermissionDeniedError` 403); any member reads and tests. Settings: `run_budget_usd` default 2.00, `0 < x ≤ 100`, 2 decimals; `max_steps` default 50, `1 ≤ x ≤ 200`; no row means defaults (`version` 0). Both tables have RLS.

Identity routes (`modules/identity/api.py`): `GET /v1/me` → `{user, workspaces: [{workspace, role}], current_workspace: {workspace, role}}`; `GET /v1/workspaces` → `{items: [{workspace, role}], next_cursor: null}`; `POST /v1/workspaces` `{name}` → `201 {workspace, role: "owner"}`; `GET /v1/settings` → `{keys: {llm, exa}, settings: {run_budget_usd, max_steps, version}}` (a key is `{kind, base_url, model, masked, last_tested_at, last_test_ok, version, updated_at}` or `null`); `PATCH /v1/settings` `{version, run_budget_usd?, max_steps?}` → settings or 409; `PUT /v1/settings/keys/{kind}` `{value, base_url?, model?}` → key; `DELETE /v1/settings/keys/{kind}` → 204; `POST /v1/settings/keys/{kind}/test` → key (ok) or 502 `provider.upstream_error` with `meta {provider, reason}`. No response ever contains a plaintext key.

## Auth and Request Scope

- `core/auth.py` (the only PyJWT import): `bearer_claims` reads `Authorization: Bearer <jwt>` and verifies HS256 only, `aud = AUTH_JWT_AUDIENCE`, required `exp`/`aud`/`sub`, 30 s leeway (`CLOCK_SKEW_SECONDS`). Claims used: `sub`, `email` (required), `name`, `picture`. Missing/invalid token → `AuthError` (`auth.unauthorized`, 401); expired → `TokenExpiredError` (`auth.token_expired`, 401). Every 401 carries `WWW-Authenticate: Bearer`. The token and header are never logged; rejections log `auth.rejected` with a `reason` (`missing`, `invalid`, `expired`, `claims`).
- The web app mints the HS256 API token with `AUTH_JWT_SECRET`; the server never reads Auth.js JWE session tokens.
- `core/db.py`: `SessionDep` = one `AsyncSession` per request (`get_request_session`, `scope="function"`), shared by every dependency and the route; committed before the response is sent, rolled back on any exception. `set_workspace(session, id)` / `set_user(session, id)` set `app.workspace_id` / `app.user_id` for the transaction.
- `modules/identity/deps.py` (exported from `metis.modules.identity`): `current_user` (`CurrentUserDep`) verifies the token, then `upsert_user_from_claims` + `ensure_personal_workspace`; invalid claims → 401. `current_workspace` (`CurrentWorkspaceDep`) reads `X-Workspace-Id` (absent → personal workspace; not a UUID → 422; not a member or unknown → `PermissionDeniedError` 403, same error for both), then sets `app.user_id` and `app.workspace_id` on the request session and binds `workspace_id`/`user_id` to logs. Returns the caller's `Membership`.
- Every `/v1` route except `/v1/health` depends on `current_user` or `current_workspace`; tenant routes use `current_workspace` so RLS is scoped.
- CORS: only `CORS_ORIGINS`, no credentials, headers `Authorization`, `Content-Type`, `X-Workspace-Id`, `Idempotency-Key`, `X-Request-ID`.
- DB roles: api and workers connect as `metis_app` (`NOSUPERUSER NOBYPASSRLS`, DML on `core` and `identity` + default privileges); migrations run as the owner. A migration adding a schema grants `metis_app` on it.

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
| Auth        | `Authorization: Bearer <Auth.js JWT>`; deps `current_user`, `current_workspace` |
| Start work  | `202 {run_id}` + `Idempotency-Key` header                                       |
| Lists       | `{items, next_cursor}`                                                          |
| Errors      | RFC 7807 `{type, title, status, detail, code}`                                  |
| Conflicts   | `version` field, `409` on mismatch                                              |
| Live events | `GET /v1/runs/{id}/events` (SSE, `Last-Event-ID`)                               |

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
| `AuthError`         | 401  |
| `TokenExpiredError` | 401  |
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
