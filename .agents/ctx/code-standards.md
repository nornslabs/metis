# Code Standards

## General

- Small, single-purpose modules; fix root causes, no workarounds.
- Respect boundaries in `architecture.md`; cross-module calls only through a module's public surface (its `__init__.py`) or adapters. `identity` may import `metis.modules.auth`; `auth` imports no module.
- Validate all external input (HTTP, LLM output, Exa, MCP) before use.
- No secrets in code, logs or tests. Config from env via settings.

## Module Structure (Standard Pattern)

Each module in `server/metis/modules/<name>/` is organised by layer. A layer is a single file while it covers one domain; once it covers several it becomes a folder with one file per domain. `auth` and `identity` use folders; `health` (one domain) uses single files.

```
modules/<name>/
├── __init__.py      # Public surface: the only thing other modules may import
├── deps.py          # FastAPI dependencies (route guards), if any
├── controller/      # HTTP routes, one file per domain; __init__ builds the module `router`
├── service/         # Business logic, one file per domain: `service.sessions.create_session`
├── repo/            # All Postgres access, one file per table: `repo.sessions.create`
├── cache/           # All Redis key/value caches, one file per cache: `cache.sessions.read` (if any)
├── models/          # SQLAlchemy models, one file per domain; __init__ re-exports them
├── dto/             # Data-transfer objects (Pydantic), one file per domain; __init__ re-exports them
├── helpers/         # Local helpers: shared by this module's files only (if any)
├── providers/       # Pluggable integrations owned by the module (or adapter.py), if any
├── events.py        # Domain events (if applicable)
└── parse.py         # Transformers/normalizers (optional)
```

The `__init__.py` of `repo/`, `cache/` and `service/` imports its submodules, so callers write `repo.sessions.get_by_hash(...)`; the folder supplies the domain, so function names do not repeat it. `models/` and `dto/` re-export every public name, so `from metis.modules.auth.dto import SessionUser` works. Files inside one layer import their siblings by module (`from ...service import sessions`), so a test can patch `service.sessions.create_session`.

### Layer Responsibilities

1. **`controller/` (Controller)**: HTTP routes only
   - Parse request, call service, return DTO; thin handlers
   - No business logic, no DB calls; never imports `repo` or `cache`
   - One file per domain with its own `APIRouter(prefix="/<domain>")` (e.g. `/workspaces`, `/settings`); route paths inside are relative to it (`""`, `"/current"`, `"/keys/{kind}"`), never repeating the prefix
   - `controller/__init__.py` builds the module's `router` with the version and module prefix (`/v1`, `/v1/auth`) and includes the domain routers

2. **`service/` (Service)**: Business logic orchestration
   - Coordinates calls between `repo`, `cache` and adapters
   - Pure business rules, no HTTP concerns
   - Never runs SQL or calls Redis directly
   - Raises domain errors from `core/errors.py`

3. **`repo/` (Repository)**: Postgres access
   - The module's only code with queries; one file per table, named after it (`repo/users.py`, `repo/sessions.py`), never `users_repo.py` beside other files
   - Queries only, no business rules; returns rows, DTOs or primitives
   - Name functions so they do not shadow SQLAlchemy's `insert`, `update`, `delete`, `select`: use `create`, `get`, `remove`

4. **`cache/` (Cache)**: Redis key/value caches
   - The module's only code that reads or writes its Redis cache keys: key prefixes, TTLs, read/write/evict
   - One file per cache (`cache/sessions.py`, `cache/oauth.py`); a new cache is a new file
   - A cache that may be lost logs Redis errors and returns a miss; a store the flow needs (e.g. one-time login state) re-raises `RedisError` for the service to map to a domain error
   - Not for queues, run event streams or locks: those stay in `core/` (`jobs`, `events`)

5. **`adapter.py` (Adapter)**: External integrations
   - HTTP clients for external APIs
   - MCP tool wrappers
   - Third-party SDK usage

6. **`dto/` (Data)**: Pydantic data-transfer objects
   - Validated inputs, records and HTTP request/response bodies
   - Called `dto`, not `schemas`: in this codebase "schema" also means a Postgres schema (`auth`, `identity`)
   - Base classes shared by all modules (`FrozenModel`, `Email`) live in `metis/helpers/dto.py`

7. **`models/` (Tables)**: SQLAlchemy models
   - One file per domain; the Postgres schema name lives in the private `models/_schema.py`

### Helpers: local and global

- **Local helpers** (`modules/<name>/helpers/`): stateless functions used by more than one file of one module (e.g. `identity/helpers/permissions.py`). Other modules must not import them (import-linter).
- **Global helpers** (`metis/helpers/`): stateless helpers that fit two or more modules as-is; they import no module (see `architecture.md`).
- A helper used by one file stays private in that file. Create `helpers/` only when a second file needs it.

### File order

Public before private: module docstring, imports, constants, then public functions and classes, then private (`_name`) functions at the bottom. A private function needed at import time (a validator used in a class body, a decorator argument, a default value) stays above its user.

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
- Test each layer independently: mock `repo` / `cache` when testing service, mock service when testing controller.