# Progress Tracker

Agents update this file when they start a PRD, when they finish it, and whenever status, a decision or an open question changes. Keep entries one line each; newest first.

## Status

- **Phase:** Hackathon MVP — in progress (M0 Foundations)
- **Active PRD:** —
- **Branch:** —
- **Last updated:** 2026-11-14 — Completed fix-foundation-gaps (SHIP-262): RLS helper fixed, RLS tests run, request_id in errors, compose fails clearly without secrets. Previously: 2026-11-13 — Completed chore-outbox-relay (SHIP-213): transactional outbox + relay job. Previously: Completed chore-redis-streams (SHIP-212): Redis Streams run event bus. Previously completed chore-arq-worker (SHIP-211): Arq agent + maintenance workers and cron scheduler. Previously 2026-11-12 — Completed CI pipeline (SHIP-210): added `.github/workflows/ci.yml` with server/web/docker/smoke jobs; README badge; fixed pre-existing ruff violations.

## External Tools

- **Docs:** Notion — `Projects` page with `Metis` → `Metis HLD` + `Metis LLD` sub-pages.
- **Issue tracking:** Linear — Metis project `P-SHIP-3` (team `SHIP`), https://linear.app/heimdallabs/project/metis-5864eaf29689

## PRD Board

| PRD | Branch | Status | Notes       |
| --- | ------ | ------ | ----------- |
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

1. `feat-auth-workspaces` — Auth.js JWT, users, workspaces, RLS
2. `feat-provider-keys` — encrypted BYO LLM + Exa keys
3. `feat-ideas-crud` — ideas, stages, runs

## Open Questions

- None yet.

## Decisions

| Date       | Decision                                                                | Why                                                                       |
| ---------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------- |
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

- SHIP-262 built on `fix/foundation-gaps`: `enable_tenant_rls` uses `format()`, and its policy is `nullif(current_setting('app.workspace_id', true), '')::uuid`. `test_rls.py` has 4 real tests running as the `metis_rls_test` role. The middleware sets `request.state.request_id`. Also fixed `MetisError` responses all being 500s (string log level). Compose requires `AUTH_JWT_SECRET`/`ENCRYPTION_MASTER_KEY` via `${VAR:?}`. Local DBs migrated earlier need `alembic downgrade base && upgrade head`. Next: `feat-auth-workspaces` (switch services to the non-superuser `metis_app` role).
- SHIP-213 built on `chore/outbox-relay`: `core/outbox.py` (`DomainEvent`, `DomainEventType`, `add_event`, `EventRegistry`/`on_event`, `relay_once`), `core/ids.py` (`uuid7`), migration `0002_core_outbox`, `outbox_relay` job wired. Fixed `core/models.py` naming convention (callables → %-format strings). Outbox tests need a migrated Postgres (`TEST_DATABASE_URL`, default `localhost:5432/metis`). Next: `feat-auth-workspaces`.
- SHIP-212 built on `chore/redis-streams`: `core/events.py` with `publish`/`read`, `RunEvent`, `RunEventType`, `MAXLEN ~ 5000`, 24 h TTL on terminal `run_status` (XADD + EXPIRE in one transaction); `MalformedEventError` (`run.event_malformed`) in `core/errors.py`. Next: SSE endpoint `GET /v1/runs/{id}/events`.
- SHIP-211 built on `chore/arq-worker`: `core/jobs.py` (enqueue, queue routing, `logged_job`), per-queue worker settings, cron scheduler, compose `worker-maintenance`. Tests need Redis (`TEST_REDIS_URL`, default `localhost:6379/15`). Next: SHIP-213 outbox relay.
- Created PR #13 at https://github.com/nornslabs/metis/pull/13
- Fixed pre-existing ruff violations in `env.py`, `test_logging.py`, `test_config.py`