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