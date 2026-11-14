# PRD: fix-foundation-gaps

Linear: SHIP-262 · https://linear.app/heimdallabs/issue/SHIP-262/fix-rls-helper-and-foundation-gaps-before-auth-and-workspaces

## Problem / Goal

A verification pass on M0 Foundations (lint, typecheck, migrations, 111 tests, health, jobs and scheduler against real Postgres and Redis) found four gaps. The first blocks tenant row-level security (RLS), which M1 (`feat-auth-workspaces`) depends on. Fix all four so M1 starts on a foundation where workspace isolation is proven, errors are traceable and the stack starts predictably.

1. **RLS helper fails in Postgres (blocker).** `enable_tenant_rls(regclass)` from migration `0001_initial` builds its policy SQL with `"current_setting('app.workspace_id')::uuid)"` in double quotes. Inside PL/pgSQL that is a quoted identifier, not a string literal, so calling the function fails and no tenant table can get RLS. The migration itself applies (the body is only checked on call), which is why it went unnoticed.
2. **Three RLS tests are hard-skipped.** `tests/core/test_rls.py` marks all three tests `@pytest.mark.skip`. Beyond hiding problem 1, the tests could not pass as written:
   - They insert text ids (`'item-a-1'`) into `UUID` columns.
   - They use `CREATE OR REPLACE POLICY`, which Postgres does not support.
   - They connect as the `postgres` superuser, and superusers bypass RLS even with `FORCE ROW LEVEL SECURITY`.
   - They read `DATABASE_URL` with a `metis_test` default, unlike the outbox tests (`TEST_DATABASE_URL`, default `.../metis`).
   - "No workspace set returns empty" cannot hold: `current_setting('app.workspace_id')` without `missing_ok` raises an error when the setting is unset.
3. **`request_id` is always `null` in error responses.** `error_handlers._get_request_id` reads `request.state.request_id`, but `RequestContextMiddleware` only binds `request_id` to the structlog context and never sets `request.state.request_id`.
4. **`docker compose up` without `.env` crashes.** Compose already marks `env_file: .env` as `required: false`. The crash comes from `Settings` validation: `AUTH_JWT_SECRET` and `ENCRYPTION_MASTER_KEY` are required, so every Python service dies with a Pydantic traceback instead of a clear message.

## User Stories

1. As a developer building M1, I want `enable_tenant_rls('<schema>.<table>'::regclass)` to work on a fresh database, so that every workspace table I add is isolated with one call.
2. As a developer, I want the helper to enable and force RLS and create the `tenant_isolation` policy on `workspace_id = app.workspace_id`, so that all tenant tables share one policy shape.
3. As a developer, I want a session with no `app.workspace_id` to see zero tenant rows, so that a missing tenant context fails closed.
4. As a developer, I want the RLS tests to run on every `uv run pytest` against a migrated Postgres, so that broken isolation fails CI instead of being skipped.
5. As a developer, I want the RLS tests to fail if the policy is removed or RLS is disabled, so that the tests prove isolation instead of passing by accident.
6. As a developer, I want the RLS tests to query as a non-superuser role, so that they exercise the same RLS rules the app will hit.
7. As a developer, I want the RLS tests to use the same `TEST_DATABASE_URL` convention as the outbox tests, so that one local setup runs all DB tests.
8. As a developer, I want the RLS tests to clean up their throwaway schema and tables, so that repeated runs stay independent.
9. As an API client, I want every `application/problem+json` error to carry a non-null `request_id`, so that I can quote it when reporting a problem.
10. As an API client, I want the `request_id` in the error body to match the `X-Request-ID` I sent, so that I can correlate my own logs.
11. As an operator, I want the `request_id` in an error body to match the `request_id` on that request's log lines, so that I can find the server-side trace from a user report.
12. As an API client, I want a generated `request_id` when I send no `X-Request-ID`, so that every error is still traceable.
13. As a developer, I want `docker compose up` without a `.env` file to stop with a clear message that names the missing variables and the fix, so that I don't have to read a Pydantic traceback.
14. As a developer, I want `docker compose up` with a `.env` copied from `.env.example` and filled in to keep working unchanged, so that the existing setup is not broken.
15. As a maintainer, I want lint, typecheck and the full test suite to stay green, so that this fix adds no regressions before M1.

## Requirements

1. **Fix the RLS helper.** Redefine `enable_tenant_rls(table_name regclass)` so the generated policy is valid SQL: `ENABLE` + `FORCE ROW LEVEL SECURITY` and policy `tenant_isolation` `FOR ALL USING (workspace_id = current_setting('app.workspace_id', true)::uuid)` in `0001_initial.py` (Decisions 1 and 2). Build the dynamic SQL with `format()` and `%s` for the regclass and a correctly escaped string literal. The verification pass already has a tested fix; reuse it.
2. **Fix and un-skip the RLS tests.** Remove the three `@pytest.mark.skip` markers and make the tests correct:
   - Use UUID ids.
   - Create policies with plain `CREATE POLICY` or, preferably, through `enable_tenant_rls`.
   - Set the workspace per transaction with `set_config('app.workspace_id', :ws, true)`, not f-string `SET LOCAL`.
   - Query as a non-superuser role (Decision 3).
   - Read `TEST_DATABASE_URL` with the same default as `test_outbox.py`.
   - Follow the outbox fixture pattern: skip only when Postgres is unreachable, never with a hard skip. CI runs `alembic upgrade head` against a Postgres service, so the tests run there.
3. **Add a "policy removed" proof.** At least one test shows the isolation assertion fails when the policy is dropped or RLS is disabled. For example, it disables RLS, sees the other workspace's rows, then re-enables RLS and sees them hidden. This meets the "fail if the policy is removed" criterion without mutation tooling.
4. **Set `request.state.request_id` in `RequestContextMiddleware`** before calling the next handler, so `_get_request_id` returns the same id the middleware binds to logs and echoes in `X-Request-ID`. This covers `MetisError`, validation, HTTP and unhandled-exception responses.
5. **Make compose fail clearly without secrets.** Interpolate the required secrets in each Python service's `environment` with compose's required-variable syntax, for example `${AUTH_JWT_SECRET:?Set AUTH_JWT_SECRET: cp .env.example .env and fill it in}`. `docker compose up` then stops before starting any container and names the variable (Decision 4). Keep `env_file` `required: false`.
6. **Docs.** Update `README.md` setup steps if the compose behavior or test setup changes, and document how to run the RLS tests locally (migrated Postgres, `TEST_DATABASE_URL`).

## Out of Scope

- Switching the running api/worker/scheduler services from the `postgres` superuser to the `metis_app` role (Decision 3). That belongs with `feat-auth-workspaces`, where tenant tables first appear.
- Setting `app.workspace_id` from the authenticated request (a session/DB dependency). This is part of `feat-auth-workspaces`.
- Any tenant table or module migration.
- Adding `X-Request-ID` to 500 responses that bypass `RequestContextMiddleware` through `ServerErrorMiddleware`. Only the body's `request_id` is in scope.
- Removing the unused `upgrade_async`/`downgrade_async` helpers in `0001_initial.py`. They call a non-existent `exec_text`, but nothing invokes them.
- Shipping dev default secrets in compose.

## Touches

- `server/migrations/versions/0001_initial.py` — fix the `enable_tenant_rls` body in place (Decision 1).
- `server/tests/core/test_rls.py` — un-skip and correct the tests.
- `server/metis/core/middleware.py` — set `request.state.request_id`.
- `server/tests/core/test_errors.py` and/or `server/tests/core/test_logging.py` — `request_id` assertions.
- `compose.yaml` — required-variable interpolation for secrets.
- `README.md` — setup and RLS test notes.

## Dependencies

- `chore-migrations-rls` (SHIP-207): done
- `chore-core-errors` (SHIP-261): done
- `feat-global-logger` (SHIP-260): done
- `chore-compose-stack` (SHIP-205): done
- `chore-outbox-relay` (SHIP-213): done (migration `0002` is the current head)

No Linear blocked-by relations.

## Testing Decisions

- **Seams (highest available, all existing):**
  1. **Postgres via SQL**: the `enable_tenant_rls` function on a migrated database, observed only through which rows a non-superuser session can see. This follows the `test_outbox.py` pattern of a real migrated Postgres fixture.
  2. **HTTP via the FastAPI test client**: the problem+json body and the `X-Request-ID` header, plus `structlog.testing.capture_logs` for the log-line match. This follows the existing `test_errors.py` and `test_logging.py` tests.
  3. **Compose CLI**: `docker compose config` with no `.env` must exit non-zero with the variable name in stderr. This is a manual or smoke check, not a pytest.
- Tests assert external behavior only: visible rows, response body and headers, and log fields. They do not check function source or middleware internals.
- RLS tests cover: A cannot read B; no workspace set returns zero rows without an error; a table set up through the helper is isolated; disabling RLS makes the isolation assertion fail.
- Error tests cover: a supplied `X-Request-ID` is echoed in the body; without the header, the body id is non-null and equals the response header; the body id equals the `request_id` on the request's log line. Cover at least one `MetisError` and the unhandled `Exception` path.

## Acceptance Criteria

- [x] The migrations apply cleanly on a fresh Postgres, and `enable_tenant_rls` enables RLS on a tenant table without error.
- [x] The 3 RLS tests run with no skip markers and pass against a migrated Postgres, including in CI.
- [x] A test demonstrates that the isolation assertion fails when the policy or RLS is removed.
- [x] Error responses include a non-null `request_id` that matches the request's log line and the `X-Request-ID` header.
- [x] `docker compose up` without `.env` fails before containers start, with a message naming the missing variables and the fix; with a filled-in `.env` it works as before.
- [x] `architecture.md` states that an unset `app.workspace_id` returns zero rows.
- [x] `uv run ruff check`, `uv run mypy`, `uv run pytest` pass; `alembic downgrade base` and `alembic upgrade head` still work.

## Decisions (resolved open questions, 2026-11-14)

1. **The helper fix lives in `0001_initial.py`, edited in place**, as the issue asks. The user explicitly allowed overriding the protected-migrations rule here, because no tenant table calls the helper yet. Local databases already at head must be reset (`alembic downgrade base && alembic upgrade head`); note this in the README and the commit body.
2. **An unset `app.workspace_id` returns zero rows.** The policy uses `current_setting('app.workspace_id', true)`, so an unset value is NULL and access fails closed with no error. Sync this into `architecture.md`.
3. **The RLS tests use a role made by the fixture.** The fixture creates (if missing) a `NOLOGIN NOSUPERUSER` role, grants it access to the throwaway schema, and queries through `SET LOCAL ROLE`. Moving the app services to `metis_app` stays with `feat-auth-workspaces`.
4. **Compose without `.env` fails with a clear error.** Required secrets use `${VAR:?message}` interpolation. Compose ships no dev default secrets.

## Implementation Notes

- **Also fixed: `MetisError` responses were all 500s.** `_handle_metis_error` passed string levels (`"info"`) to structlog's `logger.log()`, which expects an int, so it raised and the unhandled-exception handler answered instead. The new request-id tests caught it. The handler now uses `logging.INFO`/`WARNING`/`ERROR`, and a test pins `ConflictError` to 409.
- **Policy uses `nullif(current_setting('app.workspace_id', true), '')::uuid`.** After a transaction-local `set_config`, a pooled connection reads the setting back as `''`, not NULL, and `''::uuid` raises. A test covers that case, and a mutation check confirmed it fails without `nullif`.
- The middleware clears the `request_id` log context in `finally`, so a raised exception no longer leaves it bound.
- The `0001` downgrade now drops `enable_tenant_rls`. The unused async helpers share the same SQL constant, so they can't drift.
- Corrected the README: the local `postgres` superuser bypasses RLS.

## Status

done
