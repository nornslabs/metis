# Architecture Context

Metis turns an idea into: adaptive interview → Exa research → live score (6 fixed params) → spec → HLD (Notion) → phases → Linear issues. Monorepo: Python server + Next.js web. All agent work runs in one LangGraph graph inside background workers.

## Stack

| Layer       | Technology                                       | Role                                                            |
| ----------- | ------------------------------------------------ | --------------------------------------------------------------- |
| API         | FastAPI + Pydantic v2 (Python 3.12, uv)          | REST `/v1`, SSE, validation                                     |
| Agents      | LangGraph + `langchain-openai` (`base_url`)      | Supervisor + specialist ReAct agents, BYO OpenAI-compatible LLM |
| Agent state | `langgraph-checkpoint-postgres`                  | Checkpoints; pause/resume via `interrupt()`                     |
| Tools       | `exa-py`, `langchain-mcp-adapters`               | Research; Linear/Notion via MCP                                 |
| Jobs        | Arq + Redis                                      | `run_graph`, market watch, outbox relay                         |
| DB          | Postgres + pgvector, SQLAlchemy async, Alembic   | Source of truth, embeddings                                     |
| Web         | Next.js App Router + TS, Tailwind + shadcn/ui    | UI                                                              |
| Auth        | Auth.js → JWT verified by server                 | Sign-in, workspace scoping                                      |
| Client      | openapi-typescript + TanStack Query, EventSource | Typed API calls, live run events                                |

## System Boundaries

- `web/` — UI only; talks to the server API, nothing else.
- `server/metis/entrypoints/` — `api`, `worker`, `scheduler` processes; wiring only.
- `server/metis/core/` — ports (LLM, research, output, input), DB, jobs, outbox, security. No tables except `core.outbox`.
- `server/metis/agent/` — the graph: supervisor + Interviewer, Researcher, Scorer, Advisor, Architect, Planner, Integrator; tools; MCP loading; budgets.
- `server/metis/modules/<name>/` — identity, ideas, research, scoring, planning, integrations, memory, notifications. Each owns its tables; public API is `service.py`.
- `server/prompts/` — versioned specialist prompts. `server/evals/` — scoring evals.

## Run Flow

API writes intent → enqueues `run_graph(run_id)` → returns `202`. Worker runs the graph until done or `interrupt()` (status `awaiting_user`). User answer → resume with `Command(resume=...)`. Progress: graph stream → Redis → SSE.

## Storage Model

- **Postgres**: all business data (ideas, interviews, research, competitor KB, immutable score runs, specs, plans, exports, encrypted keys/tokens), one schema per module, plus LangGraph checkpoints and pgvector embeddings.
- **Redis**: ephemeral only (queues, run event streams, locks, rate limits).
- **External**: Linear issues and Notion pages via MCP; Metis stores only their ids.

## Auth and Access Model

- Users sign in via Auth.js; server verifies the JWT.
- Every tenant row has `workspace_id`, enforced by Postgres RLS. Exception: `core.outbox` carries `workspace_id` without RLS; the outbox relay reads across workspaces and no API route exposes it.
- Each idea has one owner; only the owner or workspace admins mutate it.
- LLM, Exa and MCP credentials are per workspace (BYO), encrypted, never returned or logged.

## Invariants

1. Request handlers never call LLMs, Exa or MCP; long work runs in workers.
2. Modules use each other only via `service.py`; the agent writes only through services.
3. External writes (Linear, Notion) and user decisions require an approval `interrupt()`.
4. Stages end in validated Pydantic output; score runs, specs and snapshots are immutable versions.
5. Rubric is fixed: weights 25/25/15/15/10/10; below 55 = adviser mode.
6. Every LLM/Exa call is metered against the workspace budget.
