# Metis

[![CI](https://github.com/heimdallabs/metis/actions/workflows/ci.yml/badge.svg)](https://github.com/heimdallabs/metis/actions/workflows/ci.yml)

Metis is an agentic planning application.

## Structure

- `server/`: Python backend using FastAPI, LangGraph, and Arq.
- `web/`: Next.js frontend with Tailwind CSS and shadcn/ui.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python package management.
- [Node.js](https://nodejs.org/) and `npm` for the frontend.
- [Docker](https://www.docker.com/) for local infra (Postgres, Redis).

## Development

### One command: the full stack

`docker compose up` builds and runs every service: Postgres (pgvector),
Redis, the API, the Arq worker, the scheduler, and the web app.

```bash
docker compose up --build
```

- API: `http://localhost:8000`
- Web: `http://localhost:3000`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`

A one-shot `migrate` service runs `alembic upgrade head` before the API
starts, so the schema is always current.

Create `.env` first (`cp .env.example .env`) and fill in `AUTH_JWT_SECRET` and
`ENCRYPTION_MASTER_KEY`. Without them, `docker compose up` stops before any
container starts and names the missing variable. Everything else has a compose
default (Postgres `postgres`/`postgres`, `AUTH_JWT_AUDIENCE=metis`).

#### Database Role

PostgreSQL requires a non-superuser role for Row-Level Security (RLS) to work
correctly. In production, `metis_app` is the dedicated role with only the
permissions needed for the application to function. RLS policies prevent
this role from reading or modifying other workspaces' data, even if a bug
in the application logic attempts to bypass the workspace filter.

Locally the services connect as the `postgres` superuser, and **superusers
bypass RLS** even when it is forced, so do not rely on the local stack to prove
isolation. The RLS tests query as a non-superuser role instead (see Tests).

Tenant tables get isolation from one call in their migration:
`SELECT enable_tenant_rls('<schema>.<table>'::regclass)`. It enables and forces
RLS and adds a `tenant_isolation` policy on
`workspace_id = app.workspace_id`. Set the workspace per transaction with
`SELECT set_config('app.workspace_id', '<uuid>', true)`. When it is not set,
the table returns no rows.

If your local database was migrated before SHIP-262, reset it so the fixed
helper is installed: `uv run alembic downgrade base && uv run alembic upgrade head`.

To create the production role manually:

```sql
CREATE ROLE metis_app WITH LOGIN PASSWORD 'your-secure-password';
GRANT CONNECT ON DATABASE metis TO metis_app;
GRANT USAGE ON SCHEMA identity, ideas, research, scoring, planning,
    integrations, memory, notifications, core TO metis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA
    identity, ideas, research, scoring, planning, integrations, memory,
    notifications, core TO metis_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA identity, ideas, research, scoring,
    planning, integrations, memory, notifications, core GRANT SELECT,
    INSERT, UPDATE, DELETE ON TABLES TO metis_app;
```

To tear it down:

```bash
docker compose down -v
```

### Server

```bash
cd server
uv sync
# Set up .env from .env.example
uv run uvicorn metis.entrypoints.api:app --reload
```

### Tests

```bash
cd server
uv run pytest
```

Database and Redis tests need a migrated Postgres and a Redis. They read
`TEST_DATABASE_URL` (default
`postgresql+asyncpg://postgres:postgres@localhost:5432/metis`) and
`TEST_REDIS_URL` (default `redis://localhost:6379/15`), and skip only when
those are unreachable. Run `uv run alembic upgrade head` against the test
database first. The RLS and identity tests create `NOLOGIN` non-superuser
roles (`metis_rls_test`, `metis_identity_test`) and query as them, because
superusers bypass RLS.

### Web

```bash
cd web
npm install
npm run dev
```