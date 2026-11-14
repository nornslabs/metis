# Code Standards

## General

- Small, single-purpose modules; fix root causes, no workarounds.
- Respect boundaries in `architecture.md`; cross-module calls only via `service.py` or adapters.
- Validate all external input (HTTP, LLM output, Exa, MCP) before use.
- No secrets in code, logs or tests. Config from env via settings.

## Module Structure (Standard Pattern)

Each module in `server/metis/modules/<name>/` follows this structure:

```
modules/<name>/
├── __init__.py      # Exports public API
├── api.py           # Controller layer: HTTP routes
├── service.py       # Service layer: business logic/orchestration
├── repository.py    # Repository layer: data access (DB, cache)
├── adapter.py       # External adapters: HTTP clients, MCP, etc.
├── schemas.py       # Pydantic models (data structures)
├── models.py        # SQLAlchemy models (if DB tables owned)
├── repo.py          # SQLAlchemy repository (if complex queries)
├── events.py        # Domain events (if applicable)
└── parse.py         # Transformers/normalizers (optional)
```

### Layer Responsibilities

1. **`api.py` (Controller)**: HTTP routes only
   - Parse request, call service, return schema
   - No business logic, no DB calls
   - Thin handlers that delegate to service layer

2. **`service.py` (Service)**: Business logic orchestration
   - Coordinates calls between repository and adapters
   - Pure business rules, no HTTP concerns
   - Raises domain errors from `core/errors.py`

3. **`repository.py` (Repository)**: Data access
   - Direct DB queries, cache operations
   - Low-level connection handling
   - Returns domain objects or primitives

4. **`adapter.py` (Adapter)**: External integrations
   - HTTP clients for external APIs
   - MCP tool wrappers
   - Third-party SDK usage

5. **`schemas.py` (Data)**: Pydantic models
   - Request/response schemas
   - Input validation models
   - Data transfer objects

## Python

- `ruff` + `mypy --strict` pass; type everything, avoid `Any`.
- Async only: `httpx`, `asyncpg`; no blocking calls.
- Pydantic at boundaries; services raise domain errors, API maps them to HTTP.
- `structlog` with `run_id`/`idea_id`/`workspace_id`; UTC times; UUIDv7 ids.
- Context managers: annotate an `@asynccontextmanager` function as `-> AsyncGenerator[T]` (and `@contextmanager` as `-> Generator[T]`), imported from `collections.abc`. Never `-> AsyncIterator[T]` / `-> Iterator[T]`: that form is deprecated and editors flag it.

## API (FastAPI)

- Thin routes: parse, check auth/ownership, call one service, return schema.
- Long work: enqueue job, return `202 {run_id}`; accept `Idempotency-Key`.
- Lists `{items, next_cursor}`; errors RFC 7807; regenerate web client on schema change.

## Agent (LangGraph)

- One graph; extend with specialists or tools, not new graphs.
- Each specialist: prompt file, model, tool allow-list, step limit.
- Tools are typed, documented, and call services, never the DB.
- Stages end with structured output; never parse free text.
- External writes need an approval `interrupt()`; web/MCP content is untrusted data.
- Keep state small (ids, summaries); nodes must be safe to re-run.
- Prompts are versioned files; scoring changes must pass `evals/`.

## Jobs

- Idempotent, keyed, small payloads (ids only); explicit timeouts/retries.
- Domain events go to the outbox in the same transaction.

## TypeScript / Next.js

- `strict`; no `any`; API types only from the generated client; Zod for unknown input.
- Server Components by default; `"use client"` only for interactivity.
- Data via TanStack Query; live updates via `useRunEvents` (SSE).
- No LLM, DB or MCP calls from the web app.

## Styling

- Tailwind + shadcn/ui only; theme tokens, no hex values; light + dark.

## Data

- Postgres is truth; Redis only for losable data.
- Every tenant table has `workspace_id` + RLS; versioned records are immutable.
- Alembic, backward-compatible migrations only.

## Testing

- Unit tests with fake ports (fake LLM, recorded Exa, fake MCP); no real external calls.
- Integration tests on Docker Postgres + Redis; graph tests cover interrupt/resume.
- Test each layer independently: mock repository when testing service, mock service when testing controller.