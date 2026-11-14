# Progress Tracker

Agents update this file when they start a PRD, when they finish it, and whenever status, a decision or an open question changes. Keep entries one line each; newest first.

## Status

- **Phase:** Hackathon MVP — in progress (M0 Foundations)
- **Active PRD:** —
- **Branch:** —
- **Last updated:** 2026-11-14 — Completed feat-provider-keys (SHIP-217): BYO LLM + Exa keys, key test, workspace settings. Previously: Completed feat-jwt-auth (SHIP-216): JWT auth, workspace scoping, `/me`, `metis_app` role. Previously: Completed feat-secret-encryption (SHIP-215): envelope encryption in `core/crypto.py`. Previously: Completed feat-identity-workspaces (SHIP-214): identity users, workspaces, members + RLS. Previously: Completed fix-foundation-gaps (SHIP-262): RLS helper fixed, RLS tests run, request_id in errors, compose fails clearly without secrets. Previously: 2026-11-13 — Completed chore-outbox-relay (SHIP-213): transactional outbox + relay job. Previously: Completed chore-redis-streams (SHIP-212): Redis Streams run event bus. Previously completed chore-arq-worker (SHIP-211): Arq agent + maintenance workers and cron scheduler. Previously 2026-11-12 — Completed CI pipeline (SHIP-210): added `.github/workflows/ci.yml` with server/web/docker/smoke jobs; README badge; fixed pre-existing ruff violations.

## External Tools

- **Docs:** Notion — `Projects` page with `Metis` → `Metis HLD` + `Metis LLD` sub-pages.
- **Issue tracking:** Linear — Metis project `P-SHIP-3` (team `SHIP`), https://linear.app/heimdallabs/project/metis-5864eaf29689

## PRD Board

| PRD | Branch | Status | Notes       |
| --- | ------ | ------ | ----------- |
| feat-provider-keys | feat/provider-keys | done | SHIP-217: BYO LLM + Exa keys, workspace settings |
| feat-jwt-auth | feat/jwt-auth | done | SHIP-216: JWT auth, workspace scoping, `/me`, `metis_app` role |
| feat-secret-encryption | feat/secret-encryption | done | SHIP-215: envelope encryption for BYO secrets |
| feat-identity-workspaces | feat/identity-workspaces | done | SHIP-214: identity users, workspaces, members + RLS |
| fix-foundation-gaps | fix/foundation-gaps | done | SHIP-262: RLS helper, RLS tests, request_id in errors, compose without `.env` |
| feat-global-logger | feat/global-logger | done | SHIP-260: structlog with request context middleware; merged |
| chore-core-errors | chore/core-errors | done | SHIP-261: global error handler + error code catalog; merged onto `core/config.py` |
| chore-core-config | chore/core-config | done | SHIP-259: Pydantic Settings global config |
| chore-repo-setup | integration/v1-foundations | done | SHIP-204: Monorepo skeleton and tooling |
| chore-compose-stack | chore/compose-stack | done | SHIP-205: docker compose up for full local stack |
| feat-health-route | feat/health-route-refactored | done | SHIP-208: `GET /v1/health` with proper controller-service separation |
| chore-ci-pipeline | chore/ci-pipeline | done | SHIP-210: CI pipeline (server/web/docker jobs + smoke) |
| chore-arq-worker | chore/arq-worker | done | SHIP-211: Arq worker (agent + maintenance) and scheduler |
| chore-redis-streams | chore/redis-streams | done | SHIP-212: Redis Streams run event bus (`core/events.py`) |
| chore-outbox-relay | chore/outbox-relay | done | SHIP-213: transactional outbox + relay job |

Status values: `draft`, `in progress`, `blocked`, `done`.

## Next Up (MVP build order)

1. `feat-ideas-crud` — ideas, stages, runs

## Open Questions

- None.

## Decisions

| Date       | Decision                                                                | Why                                                                       |
| ---------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| 2026-11-14 | New `metis/helpers/` for generic stateless code (`http`, `mcp`, `ids`, `validation`, `text`); rule in `architecture.md` | Adapters stay vendor-specific, `core` stays infrastructure; shared plumbing has one home |
| 2026-11-14 | Exa via its hosted MCP server (`mcp.exa.ai/mcp`, `x-api-key`), not `exa-py`; key check = one 1-result `web_search_exa` call | One pattern (MCP) for every external tool; keyless search means only a tool call proves a key |
| 2026-11-14 | Provider calls are capped at 10 s in total with `asyncio.timeout`, not only `httpx`'s per-phase timeout | A slow, trickling endpoint must not hang a request |
| 2026-11-14 | `provider_keys.kind` is text + CHECK, like `members.role`; deleting a missing key is `provider.key_not_found` 404 | Consistent with existing enums; generic 404 code is route-specific |
| 2026-11-14 | Workspace settings default `run_budget_usd` 2.00, `max_steps` 50; bounds ≤ 100 USD, 1–200 steps; row created on first PATCH (`version` 0) | Runs work right after adding keys; caps stop typo budgets |
| 2026-11-14 | Only owners change provider keys and settings; members can read and test | Keys and budget are the workspace's spend |
| 2026-11-14 | SHIP-217 tested at the HTTP seam with adapters on `httpx.MockTransport`, plus one `get_key_for_use` service check | One seam, no real provider calls |
| 2026-11-14 | Key test goes route → `identity.service.test_key` → LLM adapter (`list_models`) / Exa adapter (`check`); no provider calls in handlers | Keeps handlers thin; the adapter is reused by the SHIP-220 LLM gateway |
| 2026-11-14 | JWT verification uses PyJWT, HS256 JWS only; web (SHIP-219) mints the API token | Small, maintained lib; server stays independent of Auth.js's JWE session format |
| 2026-11-14 | SHIP-216 adds the non-superuser `metis_app` role used by api/worker | RLS must hold for real traffic, not only in tests |
| 2026-11-14 | SHIP-216 is tested at one HTTP seam with locally signed JWTs | Tests the behaviour clients see; no coupling to `core/auth.py` internals |
| 2026-11-14 | `mask(secret)` = first 3 + `…` + last 4 for secrets ≥ 12 chars, else nothing revealed | Provider stays recognisable (`sk-…a1b2`) without exposing short secrets |
| 2026-11-14 | `SecretDecryptError` (`crypto.decrypt_failed`) maps to HTTP 422, asks to re-enter the key | User can recover by saving the key again |
| 2026-11-14 | Identity services restore the caller's RLS settings after use | Transaction-local `set_config` would otherwise switch the caller's tenant scope |
| 2026-11-14 | `identity.users.auth_sub` (unique) is the upsert key for sign-in | Auth.js `sub` is stable and may not be a UUID; email can change |
| 2026-11-14 | `identity.workspaces.is_personal` + partial unique index on `(created_by) WHERE is_personal` | Postgres enforces one personal workspace per user, race-safe |
| 2026-11-14 | `identity.members` adds SELECT policy `member_self` on `app.user_id` beside `tenant_isolation` | `list_workspaces` spans workspaces; still fails closed with no context |
| 2026-11-14 | Fix `enable_tenant_rls` in `0001_initial.py` in place (protected-migration override, user-approved) | No tenant table uses the helper yet; local DBs at head must be reset |
| 2026-11-14 | Tenant policy uses `current_setting('app.workspace_id', true)`: unset ⇒ zero rows | Fail closed without erroring background jobs |
| 2026-11-14 | RLS tests query as a fixture-made NOLOGIN non-superuser role | Superusers bypass forced RLS; no new CI credentials |
| 2026-11-14 | Compose requires secrets via `${VAR:?msg}`; no dev default secrets | Clear failure instead of a Pydantic traceback; no hardcoded secrets |
| 2026-11-13 | Outbox relay decodes rows inside the failure path; an undecodable row counts attempts and dies | One bad row must not stall the oldest-first outbox forever |
| 2026-11-13 | `core.outbox` has no RLS; retry unit is the whole event; UUIDv7 from a hand-written `core/ids.py` helper | Relay reads across workspaces and the app role can't bypass RLS; idempotent handlers make whole-event retry safe; no new dependency |
| 2026-11-13 | Run event streams expire 24 h after a terminal `run_status` publish; no safety TTL yet | Callers can't forget it and the event API stays at two functions; crashed-run cleanup deferred |
| 2026-11-13 | One Arq worker process per queue (`worker`, `worker-maintenance`); `watch` queue deferred | Arq binds one queue and one `max_jobs` per process; maintenance must run at concurrency 1 |
| 2026-11-12 | One LangGraph graph: supervisor + 7 specialists with scoped tools       | Autonomous agents with controlled tool choice, interrupts and checkpoints |
| 2026-11-12 | Modular monolith, 3 processes (api, worker, scheduler)                  | 2 people, ~30 hours; modules can be split later                           |
| 2026-11-12 | Integrations via MCP (Linear, Notion)                                   | One pattern for every tool                                                |
| 2026-11-12 | OpenAI-compatible LLM adapter, Exa for research, BYO keys, free         | Pluggable providers, no hosting cost                                      |
| 2026-11-12 | Rubric fixed (25/25/15/15/10/10), adviser mode below 55, live rescoring | Comparable yet market-aware scores                                        |

## Session Notes

- SHIP-217 built on `feat/provider-keys`: migration `0005_provider_keys` (`identity.provider_keys`, `identity.workspace_settings`, both RLS), adapters `metis/adapters/{http,llm,mcp,exa}.py` (client factory, 10 s total cap, safe `UpstreamError` meta `{provider, reason}`; Exa through its hosted MCP server, `exa-py` removed), identity service `get_settings_overview`/`set_key`/`delete_key`/`test_key`/`get_key_for_use`/`update_settings` (owner-only writes), routes `GET/PATCH /v1/settings`, `PUT/DELETE /v1/settings/keys/{kind}`, `POST …/test`. New errors `ProviderNotConfiguredError`, `ProviderKeyNotFoundError`; `core.error_handlers.metis_error_response`; `Settings.is_development`. 52 HTTP-seam tests in `tests/modules/identity/test_provider_keys_api.py`; shared fixtures moved to `tests/modules/identity/conftest.py` + `api_helpers.py`. Local DBs: `alembic upgrade head`. Generic code moved to `metis/helpers/` (`http.py`, `mcp.py` from adapters; `ids.py` from core; `validation.validate_input`, `text.strip`/`strip_to_none` from identity). Next: `feat-ideas-crud`; SHIP-220 LLM gateway builds on `adapters/llm.py` + `identity.get_key_for_use`; SHIP-226 (rewritten) loads Exa MCP tools for the agents.
- SHIP-216 built on `feat/jwt-auth`: `core/auth.py` (PyJWT, HS256 only, `aud`, required `exp`, 30 s leeway; `TokenExpiredError` → 401 `auth.token_expired`; 401s carry `WWW-Authenticate: Bearer`), `core/db.py` (`SessionDep` request session committed before the response, `set_workspace`/`set_user`), `modules/identity/deps.py` (`current_user`, `current_workspace` via `X-Workspace-Id`), routes `GET /v1/me`, `GET/POST /v1/workspaces`, CORS for `CORS_ORIGINS`, migration `0004_app_role` (`metis_app`, LOGIN when `APP_DB_PASSWORD` is set; compose services connect as it). 33 HTTP-seam tests in `tests/modules/identity/test_identity_api.py`. Local DBs: run `alembic upgrade head` (with `APP_DB_PASSWORD` to log in as `metis_app`). Next: `feat-provider-keys` (SHIP-217), with routes on `CurrentWorkspaceDep`.
- SHIP-215 built on `feat/secret-encryption`: `core/crypto.py` (`SealedSecret`, `encrypt`, `decrypt`, `mask`), AES-256-GCM via `cryptography`; per-secret data key wrapped by the master key; workspace UUID bytes as AAD (wrap layer also binds `key_version`); keyring holds only v1 = `ENCRYPTION_MASTER_KEY`. `SecretDecryptError` (`crypto.decrypt_failed`, 422). 27 pure-function tests in `tests/core/test_crypto.py`. Next: `feat-auth-workspaces` (SHIP-216); SHIP-217 provider keys stores `SealedSecret` fields as columns.
- SHIP-214 built on `feat/identity-workspaces`: migration `0003_identity` (`users.auth_sub`, `workspaces.is_personal` + partial unique index, `members` with `tenant_isolation` + `member_self`), `modules/identity` (models, repo, schemas, service), errors `MemberUserNotFoundError`/`WorkspaceNotFoundError`/`AlreadyMemberError`/`EmailTakenError`. 27 service-seam tests run as the `metis_identity_test` role. Services take the caller's session, never commit, and restore RLS settings. Next: `feat-auth-workspaces` (SHIP-216): JWT → `upsert_user_from_claims` + `ensure_personal_workspace`, and the non-superuser `metis_app` role.
- SHIP-262 built on `fix/foundation-gaps`: `enable_tenant_rls` uses `format()`, and its policy is `nullif(current_setting('app.workspace_id', true), '')::uuid`. `test_rls.py` has 4 real tests running as the `metis_rls_test` role. The middleware sets `request.state.request_id`. Also fixed `MetisError` responses all being 500s (string log level). Compose requires `AUTH_JWT_SECRET`/`ENCRYPTION_MASTER_KEY` via `${VAR:?}`. Local DBs migrated earlier need `alembic downgrade base && upgrade head`. Next: `feat-auth-workspaces` (switch services to the non-superuser `metis_app` role).
- SHIP-213 built on `chore/outbox-relay`: `core/outbox.py` (`DomainEvent`, `DomainEventType`, `add_event`, `EventRegistry`/`on_event`, `relay_once`), `core/ids.py` (`uuid7`), migration `0002_core_outbox`, `outbox_relay` job wired. Fixed `core/models.py` naming convention (callables → %-format strings). Outbox tests need a migrated Postgres (`TEST_DATABASE_URL`, default `localhost:5432/metis`). Next: `feat-auth-workspaces`.
- SHIP-212 built on `chore/redis-streams`: `core/events.py` with `publish`/`read`, `RunEvent`, `RunEventType`, `MAXLEN ~ 5000`, 24 h TTL on terminal `run_status` (XADD + EXPIRE in one transaction); `MalformedEventError` (`run.event_malformed`) in `core/errors.py`. Next: SSE endpoint `GET /v1/runs/{id}/events`.
- SHIP-211 built on `chore/arq-worker`: `core/jobs.py` (enqueue, queue routing, `logged_job`), per-queue worker settings, cron scheduler, compose `worker-maintenance`. Tests need Redis (`TEST_REDIS_URL`, default `localhost:6379/15`). Next: SHIP-213 outbox relay.
- Created PR #13 at https://github.com/nornslabs/metis/pull/13
- Fixed pre-existing ruff violations in `env.py`, `test_logging.py`, `test_config.py`