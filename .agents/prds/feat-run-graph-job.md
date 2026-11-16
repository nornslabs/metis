# PRD: feat-run-graph-job

Linear: SHIP-228 · https://linear.app/heimdallabs/issue/SHIP-228/161-run-graph-job-with-interrupts-and-resume

Milestone: M2 — Ideas and agent run engine. Branch: `feat/run-graph-job`. Parent: SHIP-225 (run engine). Blocks SHIP-232 (runs API).

## Problem / Goal

The graph exists (SHIP-223) but nothing runs it. A run needs a database row that says what state it is in, a worker job that drives the graph, publishes progress to the run's event stream, pauses when the agent asks the user something, resumes from the checkpoint, can be cancelled, and survives a worker crash. Without this the API (SHIP-232) and the live stream (SHIP-225 part 3) have nothing to start or watch.

Goal: the `ideas.workflow_runs` table with its service, and the `run_graph` job that runs one run end to end (start, interrupt, resume, succeed, fail, cancel, crash recovery), with stub specialists. No HTTP routes.

## User stories

1. As an operator, I want every run recorded in `ideas.workflow_runs`, so that its state survives restarts and the API can report it.
2. As a workspace member, I want a run's rows hidden from other workspaces, so that tenants stay isolated.
3. As a developer, I want a run's status to move only along allowed transitions, so that a run cannot jump from `succeeded` back to `running`.
4. As a developer, I want a `run_graph` job that takes a run id and an optional resume value, so that start, resume and crash recovery are one entry point.
5. As an operator, I want only one worker to run a given run at a time, so that duplicate jobs cannot corrupt the checkpoint.
6. As an operator, I want that lock to expire if the worker dies, so that a crashed run is not blocked forever.
7. As a user, I want a run to show `running` as soon as the worker picks it up, so that I know work has started.
8. As a user, I want the run's progress published as events (`node_started`, `node_finished`, `token`, `tool_call`), so that the page can show it live.
9. As a user, I want streamed text delivered in small batches (about every 100 ms), so that the stream is smooth without flooding Redis.
10. As a user, I want the run to pause with status `awaiting_user` when the agent asks me something, so that the interview waits for me.
11. As a user, I want the pending question or approval stored on the run, so that the page can show it after a reload.
12. As a user, I want an `interrupt` event published when the run pauses, so that the page prompts me at once.
13. As a user, I want my answer to continue the run from the same checkpoint, so that no work is repeated.
14. As an operator, I want a run to end as `succeeded` when the graph finishes, so that finished work is visible.
15. As an operator, I want a run to end as `failed` with a stable error code when the graph raises or the step limit is hit, so that I can tell why.
16. As an operator, I want error details stored without keys, prompts or upstream bodies, so that nothing sensitive leaks.
17. As a user, I want a terminal `run_status` event published after the database row is final, so that a client that reads the run after the event sees the same status.
18. As a user, I want to cancel a run and have it stop at the next step boundary, so that I do not wait for a long run I no longer want.
19. As an operator, I want a cancelled run to end as `cancelled` with its checkpoint left in place, so that history is not lost.
20. As an operator, I want runs that were `running` when a worker died to be picked up again, so that a deploy or crash does not strand them.
21. As an operator, I want recovery to continue from the last checkpoint, not restart the run, so that finished steps are not repeated.
22. As a developer, I want the job to ignore a run that is already terminal, so that a duplicate or late job is harmless.
23. As a developer, I want the job to ignore a resume for a run that is not `awaiting_user`, so that a stale resume cannot disturb a running run.
24. As a developer, I want `max_steps` read from the workspace settings when a run starts, so that the owner's cap applies.
25. As a developer, I want the run's starting stage taken from its idea, so that a run on an `exported` idea does not start at `intake`.
26. As a developer, I want a run's events and logs tagged with `run_id` and `workspace_id`, so that I can trace one run.
27. As a maintainer, I want the whole thing tested with stub specialists, real Postgres and Redis and no LLM, so that CI spends nothing.

## Implementation Decisions

- **Table `ideas.workflow_runs`** (new migration, RLS via `enable_tenant_rls`, grants for `metis_app`): `id` (UUIDv7), `workspace_id`, `idea_id` (FK to `ideas.ideas`), `kind`, `status`, `started_at`, `finished_at`, `error` (jsonb, `{code, message}`), `pending_interrupt` (jsonb), `idempotency_key` (unique per workspace, nullable), `version`, `created_at`, `updated_at`. `status` is text + CHECK over `RunStatus`, like other enums. Also adds the FK that `ideas.llm_usage.run_id` was waiting for (SHIP-220 left it open until the runs table existed). Index on `(workspace_id, status)` for recovery and listing.
- **`RunStatus` enum** (`queued`, `running`, `awaiting_user`, `succeeded`, `failed`, `cancelled`) lives in the ideas module and replaces the `TERMINAL_RUN_STATUSES` TODO in `core/events.py`.
- **Status transitions** are a fixed table, like the idea stage table: `queued → running | cancelled`; `running → awaiting_user | succeeded | failed | cancelled`; `awaiting_user → running | cancelled`. Anything else raises a new domain error. Terminal statuses have no exits. `started_at` is set on the first `running`; `finished_at` on a terminal status; `version` bumps on every change.
- **Ideas service surface** (caller's session, never commits, scoped by workspace id as well as RLS; public through `metis.modules.ideas`): `create_run`, `get_run`, and one function per move (`mark_running`, `mark_awaiting_user(pending_interrupt)`, `mark_succeeded`, `mark_failed(error)`, `mark_cancelled`). `create_run` takes an optional `idempotency_key` and inserts a `queued` row; the idempotent-start behaviour, the "one active run per idea" rule and the HTTP routes are SHIP-232.
- **Job `run_graph(ctx, run_id, workspace_id, resume=None)`**: the workspace id is a second argument because RLS hides the row until the session knows its workspace (a deliberate change from the issue's `run_graph(run_id, resume?)`; SHIP-232 enqueues with it). Registered in `JOB_QUEUES` on the `agent` queue and in `AgentWorkerSettings.functions`; wrapped in `@logged_job`. The job is a thin wrapper over a runner in `agent/runner.py`; the code lives in a new `metis/jobs/run_graph.py` as both issues say, and the `AGENTS.md` tree gets a `jobs/` line.
- **Lock.** Redis `lock:run:{run_id}` taken with `SET NX` and an owner token; held → the job logs `run.lock_held` and returns without touching the run. A background heartbeat extends the TTL while the run is live (an LLM call inside one node can outlast any per-step refresh); released on exit only if the token still matches. TTL (60 s) and heartbeat interval (20 s) come from settings (see Resolved).
- **Start or continue.** After the lock, the job loads the run and checks status: terminal → return. Then it looks at the graph's checkpoint for `thread_id = run_id`:
  - no checkpoint → first start: load the idea's stage (`ideas.get_idea`) and the workspace's `max_steps` (through an identity public function, see Touches) and call `initial_state`;
  - `resume` given and the run is `awaiting_user` → `Command(resume=value)`;
  - checkpoint present, no resume → crash recovery: input `None`, which continues from the last checkpoint;
  - `resume` given and run not `awaiting_user` → log and return.
  The status then moves to `running` and `run_status: running` is published.
- **Transactions.** The job never holds a database transaction while the graph runs. Each status change is its own short transaction (session set to the workspace, then committed) so the API sees it at once. The graph's own checkpointer uses its own pool (SHIP-223).
- **Streaming and events.** `graph.astream(..., config={"configurable": {"thread_id": run_id}}, stream_mode=["updates", "messages", "custom", "tasks"])`. Mapping to `core.events.publish`:
  - `node_started`: a task-start chunk for a specialist node, data `{node}`;
  - `node_finished`: the specialist's custom `node_finished` event, passed through (`{node}`);
  - `token`: text from `messages` chunks, buffered and flushed about every 100 ms and when the stream ends or pauses, data `{node, text}`;
  - `tool_call`: a model message that asks for a tool, data `{node, name}` (arguments are not published);
  - `interrupt`: see below;
  - `run_status`: `{status}` plus `error` on failure.
  The supervisor is routing, not work, so it publishes no node events. Using `tasks` for `node_started` is an addition to the issue's mode list; if the installed LangGraph does not offer it, the fallback is deriving `node_started` from the supervisor's routing update.
- **Interrupt.** The `__interrupt__` update carries the question or approval payload. The job stores it in `pending_interrupt`, moves the run to `awaiting_user`, publishes `interrupt` (the payload) and then `run_status: awaiting_user`, releases the lock and returns. A non-terminal status does not start the stream TTL.
- **Finish.** Graph ends normally and the final state has `last_error` unset → `succeeded`. Final state with `last_error` set (the step limit) → `failed` with that code. Any exception → `failed` with the exception's code if it is a `MetisError`, else a new generic `run.failed`; the stored message is the catalog detail, never the raw exception text. The row is committed first, then the terminal `run_status` is published (which sets the stream TTL). Also clears `pending_interrupt`.
- **Cancel.** The API (SHIP-232) sets `cancel:{run_id}`; the job checks it before starting and after every stream chunk. Set → stop consuming the stream, mark `cancelled`, publish `run_status: cancelled`. The checkpoint stays. Cancel takes effect at a step boundary, not inside a long node.
- **Crash recovery.** A recovery function finds runs in `running` whose lock is not held and enqueues `run_graph(run_id, workspace_id)` for each, under a distinct job id (`{run_id}:recover:{n}`), because the run's original job id is still remembered by Arq and would be dropped as a duplicate. It runs from the agent worker's startup hook. Finding runs across workspaces needs a read that RLS would block; the mechanism is the `SECURITY DEFINER` function (see Resolved).
- **New errors** in `core/errors.py` and the catalog: `run.failed` (generic run failure), a run-not-found error and an illegal-run-transition error (409). SHIP-232 maps them to HTTP.
- **Docs.** `server-context.md` (workflow_runs table, status table, job signature, event data shapes, lock and cancel keys, recovery, new errors, `jobs/` folder), `architecture.md` (run flow lock and recovery), `AGENTS.md` tree (`jobs/`), tracker; Notion LLD synced.

## Testing Decisions

- **Seam:** the `run_graph` job function itself, called as Arq would (`ctx` with the Redis pool, real Postgres as `metis_app`, real Redis, real checkpointer, stub specialists or a test specialist that calls `ask_user`). It is the highest seam below the API. A good test asserts what the outside world sees: the run row's status, `pending_interrupt` and `error`; the ordered events read back from the run's Redis stream; the checkpoint continuing after a resume. It does not look at runner internals. Recovery is tested through the recovery function plus a second `run_graph` call on a fresh graph and pool.
- Tests planned:
  - Happy path: a queued run on an `intake` idea ends `succeeded`; events include `run_status: running`, a `node_started` and `node_finished` pair for each specialist in stage order, and a terminal `run_status: succeeded`; the stream gets its TTL.
  - Interrupt then resume: a run that hits `ask_user` ends the job with `awaiting_user`, the question stored, an `interrupt` event; a second job call with `resume` continues from the same checkpoint (the node that asked is not repeated from the start of the run) and ends `succeeded`. An approval interrupt does the same.
  - Resume on a run that is not `awaiting_user` is ignored; a job for a terminal run does nothing.
  - Lock: a held lock makes the job exit without changing the run; the lock is released after a normal finish and after a failure; the heartbeat keeps the key alive past the base TTL.
  - Failure: a node that raises ends `failed` with a stable code and no raw exception text; the step limit ends `failed` with `run.step_limit_reached`.
  - Cancel: flag set before the start and mid-run → `cancelled`, `run_status: cancelled`, run does not continue.
  - Crash recovery: a run left `running` with a checkpoint and no lock is re-enqueued by the recovery function with a distinct job id and continues to `succeeded`; a run whose lock is held is left alone.
  - Token batching: a fake streaming model's tokens arrive as few batched `token` events, in order, none lost.
  - Service and migration: status transition table (parametrised over `RunStatus`, so a new status fails the test), RLS isolation between workspaces, idempotency-key uniqueness per workspace, migration up/down, the `llm_usage.run_id` FK.
- **Prior art:** `tests/agent/test_interrupts.py` and `graph_helpers.py` (graph driving, fresh-graph resume), `tests/core/` for events and jobs (Redis fixtures), `tests/modules/ideas/` (`idea_helpers.py`, migration and service tests), `tests/modules/conftest.py` readiness.
- `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run lint-imports` pass.

## Out of Scope

- HTTP routes: start, resume, cancel, get, list (SHIP-232); the idempotent-start behaviour and the one-active-run-per-idea rule (SHIP-232).
- The SSE endpoint and `Last-Event-ID` reconnect (SHIP-225 part 3).
- Budget enforcement against `llm_usage` (SHIP-237); only the step limit applies.
- Real specialists, tools and MCP loading; building the `LLMGateway` for specialists (it lands with the first specialist that calls a model).
- Market-watch runs (`stage=watch`, `watch` queue).
- Writing `ideas.stage` from a run; web changes.

## Touches

`server/metis/modules/ideas/` (`models/workflow_runs.py`, `repo/workflow_runs.py`, `service/workflow_runs.py`, `dto/`, `helpers/` for the transition table, `__init__.py` exports), `server/migrations/versions/` (new `0013` workflow_runs + `llm_usage` FK), `server/metis/agent/runner.py`, `server/metis/jobs/run_graph.py` (new package), `server/metis/core/jobs.py` (`JOB_QUEUES`), `server/metis/core/events.py` (use `RunStatus`), `server/metis/core/errors.py`, `server/metis/core/config.py` (lock TTL and heartbeat), `server/metis/entrypoints/worker.py` (register job, recovery on startup), `server/metis/modules/identity/__init__.py` (export a settings getter so the job can read `max_steps` through the public surface), `server/tests/` (`agent/`, `modules/ideas/`, `core/`), `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`, `AGENTS.md`, `.env.example` and `compose.yaml` if a setting is added.

## Dependencies

- `feat-agent-graph-skeleton` (SHIP-223): done.
- `feat-ideas-crud` (SHIP-218): done.
- `chore-redis-streams` (SHIP-212), `chore-arq-worker` (SHIP-211): done.
- Blocks: SHIP-232 (runs API) and the SSE endpoint.

## Acceptance criteria

- [x] An interrupt sets `awaiting_user` and stores the question in `pending_interrupt`.
- [x] Resume continues from the same checkpoint and ends `succeeded`.
- [x] A run left `running` after a worker kill is picked up on restart and continues from its last checkpoint.
- [x] A cancel flag stops the run at the next step and marks it `cancelled`.
- [x] A stub run publishes `node_started` / `node_finished` for every specialist and a terminal `run_status`, and the stream gets its TTL.
- [x] Only one worker runs a run at a time (held lock → job exits).
- [x] Tests above pass; `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run lint-imports` pass.
- [x] `server-context.md`, `architecture.md` and `AGENTS.md` updated.

## Open questions

None open.

## Resolved

- Lock TTL: 60 s with a 20 s heartbeat (new settings), not the issue's 10 minutes, so a killed worker's lock frees quickly and startup recovery sees the run as unlocked (user, 2026-11-16).
- Stuck-run scan: a narrow `SECURITY DEFINER` SQL function in the migration returns `(run_id, workspace_id)` for runs in `running`, executable by `metis_app` only; the table keeps RLS (user, 2026-11-16).
- `workflow_runs.kind`: text + CHECK, one value now, `pipeline`; `watch` is added with market-watch (user, 2026-11-16).

## Built differently from the wording above, on purpose

- `core/events.py` keeps its `TERMINAL_RUN_STATUSES` set: `core` may not import a module, so it cannot use the ideas `RunStatus` (the TODO there stays).
- The Redis keys `lock:run:{id}` and `cancel:{id}` live in `core/run_control.py` (the API will set `cancel:`), the lock itself in `agent/run_lock.py`.
- The job takes keyword arguments (`run_id`, `workspace_id`, `resume`) so `logged_job` binds them to its logs; `ctx["run_deps"]` (`RunnerDeps`) lets tests replace the sessions, checkpoint database URL and specialists.
- Graph checkpoints are written with `durability="sync"`: the default async write could lose the last completed step on a kill or an early cancel.
- Recovery runs at agent-worker startup only; the lock's short TTL makes the run recoverable at the next restart, but no scheduler sweep exists.
- `ideas.llm_usage.run_id` now has a real FK, so existing tests that recorded usage for made-up run ids create a real run first (`make_run` in `tests/agent/llm_helpers.py`); the `app_sessions` fixture moved to `tests/modules/conftest.py` so both test trees share it.
- Identity exports `get_settings_overview` (the job's `max_steps` read); the existing function, no new one.
- `.env.example` lists `RUN_LOCK_TTL_SECONDS` and `RUN_LOCK_HEARTBEAT_SECONDS`.
- `AGENTS.md` got the `jobs/` line in its tree (git tracks it as `Agents.md`); Notion LLD is not synced yet.

## Status

done
