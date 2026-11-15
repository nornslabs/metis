# Architecture Context

Metis turns an idea into: adaptive interview → Exa research → live score (6 fixed params) → spec → HLD (Notion) → phases → Linear issues. Monorepo: Python server + Next.js web. All agent work runs in one LangGraph graph inside background workers.

## Stack

| Layer       | Technology                                       | Role                                                            |
| ----------- | ------------------------------------------------ | --------------------------------------------------------------- |
| API         | FastAPI + Pydantic v2 (Python 3.12, uv)          | REST `/v1`, SSE, validation                                     |
| Agents      | LangGraph + `langchain-openai` (`base_url`)      | Supervisor + specialist ReAct agents, BYO OpenAI-compatible LLM |
| Agent state | `langgraph-checkpoint-postgres`                  | Checkpoints; pause/resume via `interrupt()`                     |
| Tools       | `mcp`, `langchain-mcp-adapters`                  | Exa research, Linear and Notion, all via MCP                    |
| Jobs        | Arq + Redis                                      | `run_graph`, market watch, outbox relay                         |
| DB          | Postgres + pgvector, SQLAlchemy async, Alembic   | Source of truth, embeddings                                     |
| Web         | Next.js App Router + TS, Tailwind + shadcn/ui    | UI                                                              |
| Auth        | Server sessions (`HttpOnly` cookie), Google sign-in | Sign-in, workspace scoping                                  |
| Client      | openapi-typescript + TanStack Query, EventSource | Typed API calls, live run events                                |

## System Boundaries

- `web/` — UI only; talks to the server API, nothing else.
- `server/metis/entrypoints/` — `api`, `worker`, `scheduler` processes; wiring only.
- `server/metis/core/` — ports (LLM, research, output, input), DB, jobs, outbox, security. No tables except `core.outbox`.
- `server/metis/adapters/` — one file per external vendor or protocol endpoint (LLM provider, Exa MCP); they translate between Metis and that vendor and nothing else. Group adapters by how Metis connects to them: providers reached over MCP go in `adapters/mcp/` (`exa.py` today; Linear and Notion later), one file per MCP server. A new connection kind gets its own subfolder the same way.
- `server/metis/helpers/` — generic helpers: stateless functions and small classes with no business rules, no table, no request scope and no knowledge of one vendor or module (e.g. `http.py` provider HTTP plumbing, `mcp.py` MCP sessions, `ids.py` UUIDv7, `validation.py` safe 422 input validation, `text.py` string clean-up). Any layer may import them; they import only the standard library, third-party libraries and `core.errors`.
  Rule for new code: if a function or file would fit two or more modules or adapters as-is, has no business rule and holds no state or config, it goes in `helpers/` (one file per concern), not in a module, `core` or `adapters`. Infrastructure that holds state or config (DB, jobs, events, outbox, auth, crypto, logging, errors, config) stays in `core`; product rules stay in their module; test-only helpers stay under `server/tests/` (`tests/helpers/` tests the helpers themselves).
- `server/metis/agent/` — the graph: supervisor + Interviewer, Researcher, Scorer, Advisor, Architect, Planner, Integrator; tools; MCP loading; budgets.
- `server/metis/modules/<name>/` — auth, identity, ideas, research, scoring, planning, integrations, memory, notifications. Each owns its tables; its public surface is its `__init__.py`, and its layers (`controller/`, `service/`, `repo/`, `cache/`, `models/`, `dto/`, `helpers/`) are internal. `auth` owns who you are (users, sessions, sign-in identities, OAuth, providers; `auth` schema); `identity` owns where you work (workspaces, members, provider keys, settings, `current_workspace`; `identity` schema).
  Import rule: `identity → auth` only, through `metis.modules.auth` (its `__init__.py` surface); `auth` imports no other module; `core` and `helpers` import no module. Enforced by import-linter (`uv run lint-imports` in CI, contracts in `server/pyproject.toml`).
- `server/prompts/` — versioned specialist prompts. `server/evals/` — scoring evals.

## Run Flow

API writes intent → enqueues `run_graph(run_id)` → returns `202`. Worker runs the graph until done or `interrupt()` (status `awaiting_user`). User answer → resume with `Command(resume=...)`. Progress: graph stream → Redis → SSE.

## Storage Model

- **Postgres**: all business data (ideas, interviews, research, competitor KB, immutable score runs, specs, plans, exports, encrypted keys/tokens), one schema per module, plus LangGraph checkpoints and pgvector embeddings.
- **Redis**: ephemeral only (queues, run event streams, locks, rate limits, the 60 s session cache, 10 min OAuth login state). Queues, streams and locks live in `core/`; a module's caches live only in its `cache.py`.
- **External**: Exa research (hosted MCP server `https://mcp.exa.ai/mcp`, workspace key in `x-api-key`), Linear issues and Notion pages, all via MCP; Metis stores only Linear/Notion ids.

## Auth and Access Model

- Sessions (SHIP-263): the server owns sign-in and issues an opaque session token in an `HttpOnly`, `SameSite=Lax` cookie. Only its SHA-256 hash is stored (`auth.sessions`); sessions expire after `SESSION_TTL_DAYS` (30) absolute or `SESSION_IDLE_DAYS` (7) idle, and revocation applies on the next request. Users link to sign-in methods through `auth.identities` (`provider`, `subject`), so new providers don't touch users, sessions or route guards. Cookie-authenticated mutations require `X-Metis-Client: web` (CSRF). Every `/v1` route except `/v1/health` and the sign-in routes under `/v1/auth` resolves its user from the session cookie (`current_user`); there is no bearer token and no shared signing secret (JWT auth removed in SHIP-267). SSE (`GET /v1/runs/{id}/events`) uses the same cookie: `EventSource` with credentials, no separate stream token.
- Google sign-in (SHIP-265): the server runs OAuth 2.0 Authorization Code + PKCE with OpenID Connect itself (`httpx` + PyJWT, no auth SDK) under `/v1/auth/google/*`. A verified Google email is required; the first sign-in creates the user, later ones match `(provider, subject)` or link by verified email. One-time login state lives in Redis (`auth:oauth:{state}`, 10 min). Post-sign-in redirects accept only relative paths. Sign-in providers live in `modules/auth/providers/` rather than `adapters/`: they produce auth types (`ProviderProfile`) and auth errors, and `adapters/` must not import a module.
- Each request runs in one workspace: `X-Workspace-Id`, or the personal workspace when absent. The personal workspace is created lazily (SHIP-268): sign-in doesn't create it; the user's first workspace-scoped call does (`GET /v1/workspaces/current` is one) (`identity.ensure_personal_workspace`, idempotent, race-safe). Calls that aren't workspace-scoped (`/v1/workspaces`, `/v1/auth/*`) don't create it. Non-members (and unknown ids) get 403. The request session sets `app.workspace_id` and `app.user_id` before any route code runs.
- The api and workers connect as the non-superuser `metis_app` role, so RLS applies to real traffic; only migrations use the owner role.
- Every tenant row has `workspace_id`, enforced by Postgres RLS via `enable_tenant_rls(regclass)` (policy `tenant_isolation`: `workspace_id = app.workspace_id`, set per transaction with `set_config(..., true)`). An unset or empty `app.workspace_id` matches no rows (fail closed, no error). Superusers bypass RLS, so the app must connect as a non-superuser role. `identity.members` has `tenant_isolation` plus a SELECT-only `member_self` policy (`user_id = app.user_id`, same fail-closed rule) so a user can list their memberships across workspaces; `identity.workspaces` and the `auth` tables (`users`, `sessions`, `identities`) have no RLS. Exception: `core.outbox` carries `workspace_id` without RLS; the outbox relay reads across workspaces and no API route exposes it.
- Each idea has one owner; only the owner or workspace admins mutate it.
- LLM, Exa and MCP credentials are per workspace (BYO), encrypted, never returned or logged. Provider keys live in `identity.provider_keys` (RLS); only `identity.get_key_for_use` decrypts them, for the LLM gateway and the Exa MCP client. Only owners change keys and settings.

## Invariants

1. Request handlers never call LLMs, Exa or MCP; long work runs in workers. One exception: `POST /v1/settings/keys/{kind}/test` goes route → `identity.service.test_key` → the LLM adapter or the Exa MCP client for one bounded check (10 s total; the LLM check lists models and spends no tokens, the Exa check is one 1-result `web_search_exa` call).
2. Modules use each other only through the other module's public surface, its `__init__.py` (`identity` may import `metis.modules.auth`; `auth` imports no module); the agent writes only through services. Inside a module, Postgres is reached only through its `repo/` and Redis caches only through its `cache/`, both called from `service/`; `controller/` never imports them. Helpers used by one module live in its own `helpers/` and are never imported by another module.
3. External writes (Linear, Notion) and user decisions require an approval `interrupt()`.
4. Stages end in validated Pydantic output; score runs, specs and snapshots are immutable versions.
5. Rubric is fixed: weights 25/25/15/15/10/10; below 55 = adviser mode.
6. Every LLM/Exa call is metered against the workspace budget (key checks excepted; they spend no tokens or one tiny search).
