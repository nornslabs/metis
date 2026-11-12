# PRD: chore-arq-worker

Linear: SHIP-211 · https://linear.app/heimdallabs/issue/SHIP-211/071-arq-worker-and-scheduler-processes

## Problem / Goal

Background work needs a home. Today `worker` and `scheduler` are placeholders: two conflicting `WorkerSettings` (one in `core/jobs.py`, one in `entrypoints/worker.py`), a `ping` that returns a string, and a scheduler that blocks on an empty event. Services have no way to enqueue a job, and nothing proves jobs run, dedupe or shut down cleanly.

Goal: a single, tested job runtime. Services enqueue idempotently via `core/jobs.py`; the `worker` process runs jobs; the `scheduler` process only enqueues periodic jobs. This unblocks SHIP-213 (outbox relay) and later `run_graph`.

## User stories

1. As a service author, I want `enqueue(job_name, *args, job_id=...)` in `core/jobs.py`, so that I can start background work without touching Arq or Redis directly.
2. As a service author, I want enqueues with the same `job_id` to run once, so that retries and double-submits are safe.
3. As an operator, I want `agent` and `maintenance` queues, so that long agent runs never starve housekeeping.
4. As an operator, I want `maintenance` limited to concurrency 1, so that outbox relay and cleanup never overlap.
5. As a developer, I want the worker to open and close the DB engine and Redis in startup/shutdown hooks, so that jobs share pooled connections and nothing leaks.
6. As a developer, I want a `ping` job, so that I can prove the pipeline end to end in tests and locally.
7. As an operator, I want the scheduler to only enqueue (`outbox_relay` every 5 seconds, `cleanup` nightly), so that scheduling never does real work.
8. As an on-call engineer, I want every job log line bound with `job_id` and, when present, `run_id` and `workspace_id`, so that I can trace one run across processes.
9. As an on-call engineer, I want context cleared between jobs, so that ids never leak into the next job's logs.
10. As an operator, I want the worker to stop cleanly on SIGTERM, finishing or re-queuing the current job, so that deploys lose no work.
11. As a developer, I want `docker compose up` to start working `worker` and `scheduler` services, so that the local stack mirrors production.
12. As a developer, I want job and Redis settings read from `core/config.py`, so that there is one source of configuration.

## Requirements

1. `core/jobs.py`: build Arq `RedisSettings` from `REDIS_URL` via `get_settings()`; expose `enqueue(job_name, *args, job_id=None, queue=...)` returning the job handle or `None` when the id already exists (dedupe is surfaced, not an error). Remove the duplicate `WorkerSettings` there.
2. Queue names `agent` and `maintenance` defined once as constants in `core/jobs.py`. Job-to-queue routing is explicit per job.
3. `entrypoints/worker.py`: the single `WorkerSettings` (compose and CLI both use it). `on_startup` opens the DB engine and Redis into `ctx`; `on_shutdown` closes both. Registers `ping` (logs and returns `"pong"`).
4. `maintenance` worker runs with `max_jobs = 1`; `agent` worker concurrency comes from a named constant.
5. `entrypoints/scheduler.py`: Arq cron (or equivalent) that only calls `enqueue`: `outbox_relay` every 5 seconds, `cleanup` nightly. Both are enqueued with time-bucketed `job_id`s so overlapping ticks dedupe. Until SHIP-213 lands, `outbox_relay` and `cleanup` are registered as no-op stubs in the worker so enqueued jobs complete.
6. Job logging: a wrapper/hook binds `job_id` plus `run_id`/`workspace_id` (when present in job kwargs) using `core.logging.bind_context`, and clears them after the job.
7. `compose.yaml`: `worker` and `scheduler` commands point at the new entrypoints (and one worker service per queue if Open question 1 is resolved that way).
8. Graceful shutdown: on SIGTERM the worker stops taking jobs, waits for or re-queues the in-flight job, then closes resources and exits 0.

## Out of scope

- Real `outbox_relay` logic (SHIP-213), `cleanup` logic, `run_graph`, `market_scan`, `distill_guidance`.
- The `watch` queue and the 15-minute market-watch tick.
- Per-run Redis locks.
- Job retry/backoff policy beyond Arq defaults.
- Metrics, tracing, Sentry hooks.

## Touches

`server/metis/core/jobs.py`, `server/metis/entrypoints/worker.py`, `server/metis/entrypoints/scheduler.py`, `server/tests/core/`, `compose.yaml`, `.agents/ctx/server-context.md` (queue/entrypoint notes).

## Dependencies

None. Blocks `SHIP-213` (outbox relay job).

## Test seam

One seam, the highest available: `core.jobs.enqueue` against a real Redis, with an Arq `Worker` run in-process. Tests assert only observable outcomes (job result, run count, process exit), not internals. Prior art: `tests/core/test_logging.py` for log assertions; `tests/modules/test_health.py` for the style.

## Acceptance criteria

- [x] Enqueuing `ping` from a test lands in the worker and completes with result `"pong"`.
- [x] Enqueuing the same `job_id` twice runs the job once.
- [x] Worker started as a subprocess exits 0 on SIGTERM; an in-flight job either finishes or is re-queued and then runs on the next worker.
- [x] `maintenance` jobs never run concurrently (two enqueued slow jobs run serially).
- [x] Job logs contain `job_id`, and `run_id`/`workspace_id` when passed; none leak into the next job.
- [x] Scheduler enqueues `outbox_relay` and `cleanup` on their cadence and does nothing else.
- [x] `docker compose up` starts `worker` and `scheduler` and the stub jobs complete.
- [x] `uv run ruff check`, `uv run mypy`, `uv run pytest` pass.

## Open questions

None. Resolved 2026-11-13:

1. Two worker processes, one per queue: `AgentWorkerSettings` and `MaintenanceWorkerSettings` in `entrypoints/worker.py`, compose services `worker` and `worker-maintenance`.
2. `watch` queue deferred to the market-watch PRD.
3. No-op `outbox_relay` and `cleanup` stubs registered in the maintenance worker; SHIP-213 replaces `outbox_relay`.

## Status

done
