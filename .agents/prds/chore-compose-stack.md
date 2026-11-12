# PRD: chore-compose-stack

## Problem / Goal

Run the whole Metis stack locally with one command: `docker compose up`.

## User stories

- As a developer, I want `docker compose up` to bring up the full stack (postgres, redis, api, worker, scheduler, web) so I don't have to start each service by hand.
- As a developer, I want the API and web to be reachable on localhost so I can iterate end to end.
- As a developer, I want Postgres to have the `vector` extension available so pgvector and LangGraph checkpoints work.

## Requirements

1. `server/Dockerfile`: multi-stage, Python 3.12 slim, install with `uv sync --frozen`, non-root user. Command is chosen per service.
2. `web/Dockerfile`: multi-stage Node 22, `next build` with standalone output, non-root user.
3. Root `compose.yaml` with services: `postgres` (`pgvector/pgvector:pg16`, volume, healthcheck), `redis` (`redis:7`, healthcheck), `api` (uvicorn `metis.entrypoints.api:app`, port 8000), `worker` (arq), `scheduler`, `web` (port 3000).
4. All services read `.env`; `api`, `worker`, `scheduler` wait for postgres and redis to be healthy.
5. Add a `migrate` one-shot service (or entrypoint step) that runs `alembic upgrade head` before api starts.
6. Document `docker compose up` in `README.md`.

## Out of scope

Production deploy (M7), health route logic.

## Touches

`compose.yaml`, `server/Dockerfile`, `web/Dockerfile`, `.dockerignore` files, `README.md`, `.env.example`, `server/migrations/env.py`, `server/metis/core/jobs.py`, `server/metis/entrypoints/api.py`, `server/metis/entrypoints/scheduler.py`, `server/metis/entrypoints/worker.py`.

## Dependencies

Blocked by: Scaffold monorepo and tooling (SHIP-204, done).

## Acceptance criteria

- `docker compose up` starts all six services with no crash loops.
- Postgres has the `vector` extension available.
- Web is reachable on `localhost:3000`, API on `localhost:8000`.

## Status

in progress