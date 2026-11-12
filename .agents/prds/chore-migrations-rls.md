# PRD: chore-migrations-rls

Linear: SHIP-207 · https://linear.app/heimdallabs/issue/SHIP-207/04-database-migrations-and-row-level-security-pattern

## Problem / Goal

Set up Alembic and a reusable row-level security (RLS) pattern so every tenant table is isolated by workspace. Today the compose stack runs a one-shot `migrate` service that invokes `alembic upgrade head`, but there is no migrations directory, no schema, no RLS, and no tenant isolation. Every future module table must inherit workspace isolation by construction.

## User Stories

1. As a developer, I want `alembic upgrade head` to create all module schemas on a fresh database, so that the stack starts with a valid schema instead of empty tables.
2. As a developer, I want `alembic downgrade base` to roll everything back cleanly, so that I can iterate on migrations without leaving orphaned objects.
3. As a developer, I want a single `enable_tenant_rls(table)` helper that later migrations reuse, so that every tenant table gets the same isolation policy without copy-paste.
4. As a developer, I want the app to connect with a non-superuser role, so that RLS cannot be bypassed by accident and no migration can accidentally grant broad privileges.
5. As a developer, I want the non-superuser role documented in `README.md`, so that anyone running the stack locally knows which credentials to use.
6. As a developer, I want a `TenantMixin` on the SQLAlchemy `Base`, so that every model that opts in gets `id` (UUIDv7), `workspace_id`, `created_at` and `updated_at` for free.
7. As a developer, I want the `Base` to carry naming conventions (snake_case table names, lowercase indexes, `ix_<table>_<col>`), so that generated DDL is consistent and predictable.
8. As a developer, I want a test that proves workspace A cannot read workspace B's rows, so that tenant isolation is verified, not assumed.

## Requirements

1. **Alembic init** in `server/migrations/` with the async env, reading `DATABASE_URL` from settings (the existing `env.py` already resolves `DATABASE_URL` from the environment over `alembic.ini`; wire it to `get_settings()` so it is the single source of truth).
2. **First migration** (`0001_initial`): create extensions `vector` and `pgcrypto`; create all module schemas: `identity`, `ideas`, `research`, `scoring`, `planning`, `integrations`, `memory`, `notifications`, plus `core` for the outbox.
3. **`enable_tenant_rls(table)` helper** used by later migrations: `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and a policy `workspace_id = current_setting('app.workspace_id')::uuid`.
4. **App DB role** that is not a superuser (RLS must not be bypassable); document it in `README.md`.
5. **SQLAlchemy `Base`** with naming conventions and a `TenantMixin` (`id` UUIDv7, `workspace_id`, `created_at`, `updated_at`).
6. **Test**: a throwaway tenant table with RLS returns only rows of the workspace set on the session.

## Out of Scope

- Module tables (each module adds its own migration later).
- Auth implementation, users, workspaces, provider keys (those PRDs follow).
- The agent graph, jobs, and web UI.

## Touches

- `server/migrations/**` — Alembic env, `0001_initial` migration, `enable_tenant_rls` helper.
- `server/alembic.ini` — keep `script_location = migrations`, URL resolved from settings.
- `server/metis/core/db.py` — engine/session factory, app role connection.
- `server/metis/core/models.py` — `Base` with naming conventions and `TenantMixin`.
- `server/tests/core/test_rls.py` — RLS isolation test.
- `README.md` — document the non-superuser app role.

## Dependencies

Blocked by: Compose stack and Dockerfiles (SHIP-205, done); Core infrastructure (SHIP-259 config, SHIP-261 errors, SHIP-208 health route — all done).

## Acceptance Criteria

- [x] `alembic upgrade head` and `alembic downgrade base` both work on a fresh DB.
- [x] RLS test proves workspace A cannot read workspace B rows.
- [x] App connects with the non-superuser role.

## Status

done