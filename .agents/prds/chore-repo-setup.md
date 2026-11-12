# PRD: chore-repo-setup

## Problem / Goal

Create the Metis monorepo skeleton so both apps build and lint from day one. This is the foundational ticket for the entire project.

## User stories

As a developer,
I want a monorepo with `server/` (Python) and `web/` (Next.js) that passes all linters and type checkers,
So that I can start building features with a consistent tooling setup.

## Requirements

### Root layout
- `AGENTS.md` — entry point for agents
- `.agents/ctx/` — project context (source of truth)
  - `project-overview.md` — what Metis is, flow, features, scope, success criteria
  - `architecture.md` — stack, boundaries, storage, auth, invariants
  - `server-context.md` — server primitives: processes, ports, enums, modules, agent graph, API/job/error conventions
  - `code-standards.md` — coding rules for Python, LangGraph, TypeScript, data, tests
- `.agents/prds/` — one file per unit of work
- `.agents/progress-tracker.md` — done / in progress / open questions
- `.gitignore` — ignore secrets, Python cache, node modules, etc.
- `README.md` — repo overview and quick start

### Server (`server/`)
- Initialize with `uv init` (Python 3.12)
- Package name: `metis`
- Structure:
  - `core/` — ports, DB, jobs, outbox, security
  - `modules/` — business logic modules
  - `agent/` — LangGraph graph, specialists, tools
  - `adapters/` — vendor adapters (LLM, research, output, input)
  - `entrypoints/` — `api.py`, `worker.py`, `scheduler.py`
  - `prompts/` — versioned specialist prompts
  - `evals/` — scoring evals
  - `tests/` — unit and integration tests
- Dependencies:
  - Runtime: fastapi, uvicorn, pydantic v2, pydantic-settings, sqlalchemy[asyncio], asyncpg, alembic, redis, arq, structlog, langgraph, langchain-openai, langgraph-checkpoint-postgres, exa-py, langchain-mcp-adapters
  - Dev: ruff, mypy, pytest, pytest-asyncio, httpx
- Configuration:
  - `pyproject.toml` with `ruff` configured
  - `pyproject.toml` with `mypy --strict` configured
  - One passing smoke test in `server/tests/`

### Web (`web/`)
- `create-next-app` with:
  - App Router
  - TypeScript strict
  - Tailwind CSS
- Initialize shadcn/ui
- Add scripts:
  - `lint` — ESLint
  - `typecheck` — TypeScript
  - `build` — production build
- Base structure:
  - `app/` — Next.js app router pages and layouts
  - `components/` — reusable React components
  - `lib/` — utilities
  - `public/` — static assets

### Environment
- `.env.example` at root listing every env var from `server-context.md` (no real values)
- `.env` is ignored (gitignored)

## Out of scope

- Docker (separate issue)
- Database (separate issue)
- CI/CD (separate issue)
- Actual implementation of any features

## Touches

- Root layout: `AGENTS.md`, `.agents/`, `.gitignore`, `README.md`
- Server: `server/pyproject.toml`, `server/metis/**`
- Web: `web/package.json`, `web/tsconfig.json`, `web/app/**`, `web/components/**`

## Dependencies

None. This is the first ticket.

## Acceptance criteria

- `uv run ruff check`, `uv run mypy`, `uv run pytest` pass in `server/`.
- `npm run lint`, `npm run typecheck`, `npm run build` pass in `web/`.
- No secrets committed; `.env` is ignored.
- All context files exist in `.agents/ctx/`.

## Status

in progress
