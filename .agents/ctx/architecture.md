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
| Auth        | Auth.js → JWT verified by server                 | Sign-in, workspace scoping                                      |
| Client      | openapi-typescript + TanStack Query, EventSource | Typed API calls, live run events                                |

## System Boundaries

- `web/` — UI only; talks to the server API, nothing else.
- `server/metis/entrypoints/` — `api`, `worker`, `scheduler` processes; wiring only.
- `server/metis/core/` — ports (LLM, research, output, input), DB, jobs, outbox, security. No tables except `core.outbox`.
- `server/metis/adapters/` — one file per external vendor or protocol endpoint (LLM provider, Exa MCP); they translate between Metis and that vendor and nothing else. Group adapters by how Metis connects to them: providers reached over MCP go in `adapters/mcp/` (`exa.py` today; Linear and Notion later), one file per MCP server. A new connection kind gets its own subfolder the same way.
- `server/metis/helpers/` — generic helpers: stateless functions and small classes with no business rules, no table, no request scope and no knowledge of one vendor or module (e.g. `http.py` provider HTTP plumbing, `mcp.py` MCP sessions, `ids.py` UUIDv7, `validation.py` safe 422 input validation, `text.py` string clean-up). Any layer may import them; they import only the standard library, third-party libraries and `core.errors`.
  Rule for new code: if a function or file would fit two or more modules or adapters as-is, has no business rule and holds no state or config, it goes in `helpers/` (one file per concern), not in a module, `core` or `adapters`. Infrastructure that holds state or config (DB, jobs, events, outbox, auth, crypto, logging, errors, config) stays in `core`; product rules stay in their module; test-only helpers stay under `server/tests/` (`tests/helpers/` tests the helpers themselves).
- `server/metis/agent/` — the graph: supervisor + Interviewer, Researcher, Scorer, Advisor, Architect, Planner, Integrator; tools; MCP loading; budgets.
- `server/metis/modules/<name>/` — identity, ideas, research, scoring, planning, integrations, memory, notifications. Each owns its tables; public API is `service.py`.
- `server/prompts/` — versioned specialist prompts. `server/evals/` — scoring evals.

## Run Flow

API writes intent → enqueues `run_graph(run_id)` → returns `202`. Worker runs the graph until done or `interrupt()` (status `awaiting_user`). User answer → resume with `Command(resume=...)`. Progress: graph stream → Redis → SSE.

## Storage Model

- **Postgres**: all business data (ideas, interviews, research, competitor KB, immutable score runs, specs, plans, exports, encrypted keys/tokens), one schema per module, plus LangGraph checkpoints and pgvector embeddings.
- **Redis**: ephemeral only (queues, run event streams, locks, rate limits).
- **External**: Exa research (hosted MCP server `https://mcp.exa.ai/mcp`, workspace key in `x-api-key`), Linear issues and Notion pages, all via MCP; Metis stores only Linear/Notion ids.

## Auth and Access Model

- Users sign in via Auth.js; the web app sends an HS256 JWT (`aud` = `AUTH_JWT_AUDIENCE`, `exp`, 30 s leeway) as `Authorization: Bearer`, and the server verifies it on every `/v1` request except `/v1/health`. The verified `sub` maps to an identity user with a personal workspace.
- Each request runs in one workspace: `X-Workspace-Id`, or the personal workspace when absent. Non-members (and unknown ids) get 403. The request session sets `app.workspace_id` and `app.user_id` before any route code runs.
- The api and workers connect as the non-superuser `metis_app` role, so RLS applies to real traffic; only migrations use the owner role.
- Every tenant row has `workspace_id`, enforced by Postgres RLS via `enable_tenant_rls(regclass)` (policy `tenant_isolation`: `workspace_id = app.workspace_id`, set per transaction with `set_config(..., true)`). An unset or empty `app.workspace_id` matches no rows (fail closed, no error). Superusers bypass RLS, so the app must connect as a non-superuser role. `identity.members` has `tenant_isolation` plus a SELECT-only `member_self` policy (`user_id = app.user_id`, same fail-closed rule) so a user can list their memberships across workspaces; `identity.users` and `identity.workspaces` have no RLS. Exception: `core.outbox` carries `workspace_id` without RLS; the outbox relay reads across workspaces and no API route exposes it.
- Each idea has one owner; only the owner or workspace admins mutate it.
- LLM, Exa and MCP credentials are per workspace (BYO), encrypted, never returned or logged. Provider keys live in `identity.provider_keys` (RLS); only `identity.get_key_for_use` decrypts them, for the LLM gateway and the Exa MCP client. Only owners change keys and settings.

## Invariants

1. Request handlers never call LLMs, Exa or MCP; long work runs in workers. One exception: `POST /v1/settings/keys/{kind}/test` goes route → `identity.service.test_key` → the LLM adapter or the Exa MCP client for one bounded check (10 s total; the LLM check lists models and spends no tokens, the Exa check is one 1-result `web_search_exa` call).
2. Modules use each other only via `service.py`; the agent writes only through services.
3. External writes (Linear, Notion) and user decisions require an approval `interrupt()`.
4. Stages end in validated Pydantic output; score runs, specs and snapshots are immutable versions.
5. Rubric is fixed: weights 25/25/15/15/10/10; below 55 = adviser mode.
6. Every LLM/Exa call is metered against the workspace budget (key checks excepted; they spend no tokens or one tiny search).
