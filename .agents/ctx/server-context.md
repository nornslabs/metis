# Server Context

## Runtime Model

One Python codebase (`server/metis`), one Docker image, three logical processes (the worker runs as one container per queue). API records intent and streams; workers do all agent work; scheduler only enqueues.

| Process     | Entrypoint                 | Job                                                |
| ----------- | -------------------------- | -------------------------------------------------- |
| `api`       | `entrypoints/api.py`       | FastAPI REST `/v1`, SSE, auth                      |
| `worker`    | `entrypoints/worker.py`    | Arq jobs: `run_graph`, `market_scan`, outbox relay; one process per queue (`AgentWorkerSettings`, `MaintenanceWorkerSettings`) |
| `scheduler` | `entrypoints/scheduler.py` | Market-watch ticks (15 min), nightly jobs          |

## Configuration

All config via env, loaded into `core/config.py` (pydantic-settings). No hardcoded values.

| Purpose          | Env var                                                   |
| ---------------- | --------------------------------------------------------- |
| Postgres         | `DATABASE_URL`                                            |
| Redis            | `REDIS_URL`                                               |
| JWT verification | `AUTH_JWT_SECRET`, `AUTH_JWT_AUDIENCE`                    |
| Key encryption   | `ENCRYPTION_MASTER_KEY`                                   |
| Web origin       | `CORS_ORIGINS` (comma-separated, e.g. `http://localhost:3000,http://localhost:8000`) |
| Tracing          | `LANGFUSE_*`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `SENTRY_DSN` |

LLM and Exa keys are not env vars: they are per workspace (BYO), stored encrypted.

## Ports

Core interfaces in `core/ports.py`. Adapters implement them; nothing else imports a vendor SDK.

| Port             | MVP adapter                                  | Used by                     |
| ---------------- | -------------------------------------------- | --------------------------- |
| `LLMProvider`    | OpenAI-compatible (`ChatOpenAI`, `base_url`) | agent graph                 |
| `ResearchSource` | Exa (`exa-py`)                               | Researcher, Scorer, Advisor |
| `OutputSink`     | Linear MCP, Markdown                         | Integrator                  |
| `InputChannel`   | Web (REST + SSE)                             | API                         |

## Domain Primitives

| Primitive        | Values                                                                                                                 |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------- |
| IDs              | UUIDv7; every tenant row has `workspace_id`                                                                            |
| `Stage`          | `intake`, `interviewing`, `researching`, `scoring`, `advising`, `spec_draft`, `spec_confirmed`, `planning`, `exported` |
| `RunStatus`      | `queued`, `running`, `awaiting_user`, `succeeded`, `failed`, `cancelled`                                               |
| `RunEventType`   | `node_started`, `node_finished`, `token`, `tool_call`, `interrupt`, `run_status`                                       |
| `ScoreParam`     | `problem_severity` 25, `uniqueness` 25, `market_demand` 15, `value` 15, `feasibility` 10, `timing` 10                  |
| `ScoreBand`      | `build` (75+), `promising` (55–74), `advise` (<55)                                                                     |
| `ScoreTrigger`   | `manual`, `scheduled`, `signal`                                                                                        |
| `SignalKind`     | `new_competitor`, `shutdown`, `funding`, `trend`                                                                       |
| `SuggestionKind` | `feature`, `niche`, `pricing`, `pivot`                                                                                 |
| `ExportMode`     | `export`, `rebalance`                                                                                                  |
| Estimates        | Fibonacci points 1, 2, 3, 5, 8 (split above 8)                                                                         |

Immutable, versioned: score runs, spec versions, research snapshots.

## Modules

`modules/<name>/` with `api.py`, `service.py` (public), `models.py`, `repo.py`, `schemas.py`, `events.py`. Each owns one Postgres schema.

| Module          | Owns                                             |
| --------------- | ------------------------------------------------ |
| `identity`      | users, workspaces, provider keys, settings       |
| `ideas`         | ideas, interview turns, specs, workflow runs     |
| `research`      | snapshots, items, competitor KB, signals         |
| `scoring`       | score runs, params, suggestions, rubric versions |
| `planning`      | HLD, phases, tasks, task deps, plan diffs        |
| `integrations`  | MCP connections, export jobs, external refs      |
| `memory`        | memories (pgvector), guidance versions           |
| `notifications` | in-app notifications                             |

## Agent Graph

One LangGraph `StateGraph` in `agent/graph.py`, compiled with `AsyncPostgresSaver` (`thread_id` = run id).

| Specialist  | Tools                                                                                                           |
| ----------- | --------------------------------------------------------------------------------------------------------------- |
| Supervisor  | none; routes on `MetisState.stage`                                                                              |
| Interviewer | `ask_user`, `recall_memory`, `save_interview_turn`                                                              |
| Researcher  | `exa_search`, `exa_get_contents`, `exa_find_similar`, `kb_lookup`, `kb_upsert_competitor`, `save_research_item` |
| Scorer      | `exa_search`, `kb_lookup`, `get_rubric`, `submit_scores`                                                        |
| Advisor     | `exa_search`, `kb_lookup`, `save_suggestion`                                                                    |
| Architect   | `recall_memory`, `save_spec`, `save_hld`, Notion MCP                                                            |
| Planner     | `save_plan`, Linear MCP (read)                                                                                  |
| Integrator  | Linear MCP (write, after approval)                                                                              |

- `ask_user` and approvals call `interrupt()`; resume with `Command(resume=value)`.
- State holds ids and summaries only. Stream with `astream(stream_mode=["updates","messages","custom"])`.

## API Conventions

| Concern     | Rule                                                                            |
| ----------- | ------------------------------------------------------------------------------- |
| Prefix      | `/v1`                                                                           |
| Auth        | `Authorization: Bearer <Auth.js JWT>`; deps `current_user`, `current_workspace` |
| Start work  | `202 {run_id}` + `Idempotency-Key` header                                       |
| Lists       | `{items, next_cursor}`                                                          |
| Errors      | RFC 7807 `{type, title, status, detail, code}`                                  |
| Conflicts   | `version` field, `409` on mismatch                                              |
| Live events | `GET /v1/runs/{id}/events` (SSE, `Last-Event-ID`)                               |

## Jobs and Events

| Queue         | Jobs                                          | Notes                    |
| ------------- | --------------------------------------------- | ------------------------ |
| `agent`       | `run_graph(run_id, resume?)`                  | one per run (Redis lock) |
| `watch`       | `run_graph` with `stage=watch`                | keyed `idea_id:date`     |
| `maintenance` | `outbox_relay`, `distill_guidance`, `cleanup` | single concurrency (`max_jobs=1`), own worker process |

Enqueue only through `core.jobs.enqueue(job_name, *args, job_id=...)`; a job must be listed in `JOB_QUEUES`. The same `job_id` enqueues once. Job functions use `@logged_job` (binds `job_id`, `run_id`, `workspace_id`). The `watch` queue lands with market-watch. Scheduler is an Arq cron worker whose jobs only enqueue (`outbox_relay` every 5 s, `cleanup` nightly 03:00 UTC).

Run events go through `core.events`: `publish(run_id, type, data)` appends to the Redis stream `run:{run_id}` (`MAXLEN ~ 5000`); `read(run_id, after_id, block_ms)` does one `XREAD` and yields `RunEvent{id, run_id, type, data, ts}`. The Redis entry id is the SSE event id (`Last-Event-ID`). Publishing a terminal `run_status` (`succeeded`, `failed`, `cancelled`) sets a 24 h TTL on the stream.

Domain events (`IdeaSubmitted`, `ScoreComputed`, `SpecConfirmed`, `PlanReady`, `ExportFinished`, `MarketSignalDetected`) go to `core.outbox` in the same transaction.

## Errors

Services raise domain errors from `core/errors.py`; API maps them to HTTP.

| Error               | HTTP |
| ------------------- | ---- |
| `NotFound`          | 404  |
| `Forbidden`         | 403  |
| `IllegalTransition` | 409  |
| `VersionConflict`   | 409  |
| `BudgetExceeded`    | 402  |
| `ProviderError`     | 502  |
| `ValidationError`   | 422  |

## Observability

`structlog` JSON logs bound with `run_id`, `idea_id`, `workspace_id`. OpenTelemetry traces, Langfuse for LLM calls and cost, Sentry for exceptions. Never log keys, tokens or prompts containing them.
