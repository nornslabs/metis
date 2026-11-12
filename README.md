# Metis

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
 starts, so the schema is always current. Services read `.env` when present
 (`cp .env.example .env`); without it, compose defaults (postgres/postgres)
 apply.

#### Database Role

PostgreSQL requires a non-superuser role for Row-Level Security (RLS) to work
correctly. In production, `metis_app` is the dedicated role with only the
permissions needed for the application to function. RLS policies prevent
this role from reading or modifying other workspaces' data, even if a bug
in the application logic attempts to bypass the workspace filter.

For local development, the default `postgres` user works but RLS policies
are still enforced when `app.workspace_id` is set in the session.

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

### Web

```bash
cd web
npm install
npm run dev
```