# PRD: chore-redis-streams

Linear: SHIP-212 · https://linear.app/heimdallabs/issue/SHIP-212/072-redis-streams-event-bus-for-run-events

## Problem / Goal

The architecture says progress flows "graph stream → Redis → SSE" and `GET /v1/runs/{id}/events` resumes with `Last-Event-ID`, but nothing carries run events today. The worker has no place to publish progress, and the API has nothing to read from or resume against.

Goal: a small event bus in `core/events.py`, built on Redis Streams. The worker publishes ordered run events. The API reads them from the start or after a given id, waiting up to a set time for new ones. Each stream expires 24 hours after its run ends. This unblocks the SSE endpoint and `run_graph` streaming.

## User stories

1. As a worker author, I want `publish(run_id, type, data)`, so that I can emit run progress without touching Redis directly.
2. As a worker author, I want each publish to return the event id, so that I can log or correlate what I emitted.
3. As an API author, I want `read(run_id, after_id, block_ms)` to yield events in publish order, so that the SSE stream matches what happened.
4. As an API author, I want the Redis entry id to be the SSE event id, so that `Last-Event-ID` maps straight to a stream position with no translation table.
5. As a web user who lost the connection, I want the stream to resume after my last event id, so that I miss nothing and see nothing twice.
6. As a web user who opens a run page late, I want to read from the start, so that I see the full run history while the stream exists.
7. As an API author, I want a blocking read that returns as soon as a new event arrives, so that SSE latency stays low without busy polling.
8. As an API author, I want a blocking read with no new events to return empty after `block_ms`, so that the endpoint can send keep-alives and check for disconnects.
9. As a developer, I want a typed `RunEvent{id, run_id, type, data, ts}` envelope, so that producers and consumers agree on one shape.
10. As a developer, I want event types (`node_started`, `node_finished`, `token`, `tool_call`, `interrupt`, `run_status`) defined once as an enum, so that typos fail at type-check time, not in the browser.
11. As an operator, I want each stream capped at about 5000 entries, so that a chatty run (for example many `token` events) cannot exhaust Redis memory.
12. As an operator, I want a stream to expire 24 hours after its run ends, so that Redis stays ephemeral as the architecture requires.
13. As an operator, I want the Redis connection to come from `REDIS_URL` in `core/config.py`, so that there is one source of configuration.
14. As a developer, I want to pass in an existing Redis client (for example the worker's `ctx` client), so that publishing reuses pooled connections.
15. As a developer, I want malformed stream entries to raise a clear error instead of producing a half-built event, so that bad data is visible.

## Requirements

1. `server/metis/core/events.py`: `publish(run_id, type, data, *, redis=None) -> str` runs `XADD run:{run_id} MAXLEN ~ 5000` with fields `type`, `data` (JSON) and `ts` (UTC ISO-8601), and returns the entry id.
2. `read(run_id, after_id="0", block_ms=None, *, redis=None)` is an async iterator. It runs one `XREAD` on `run:{run_id}` after `after_id` and yields `RunEvent`s in stream order. With `block_ms` it waits up to that many milliseconds for new entries and yields nothing on timeout. The SSE endpoint calls it in a loop; `read` itself does not loop forever.
3. `RunEvent` Pydantic v2 model with `id: str` (the Redis entry id), `run_id`, `type: RunEventType`, `data: dict[str, Any]`, `ts: datetime`. `RunEventType` is a `StrEnum` with exactly `node_started`, `node_finished`, `token`, `tool_call`, `interrupt`, `run_status`.
4. The `read` iterator yields `RunEvent`, which carries the issue's `(event_id, type, data)` triple plus `run_id` and `ts`.
5. Expiry: when `publish` emits a `run_status` event whose `data.status` is a terminal `RunStatus` (`succeeded`, `failed`, `cancelled`), it also sets `EXPIRE 86400` (24 hours, a named constant) on the stream. Other events never set a TTL.
6. Stream key format `run:{run_id}` and the `MAXLEN` cap are named constants in `core/events.py`.
7. Redis client: an async client from `redis.asyncio` built from `get_settings().redis_url` when none is passed. A passed-in client is used as is and never closed by `core/events.py`.
8. Decoding: an entry with an unknown `type`, invalid JSON `data` or a missing field raises `MalformedEventError` (`run.event_malformed`, defined in `core/errors.py`) rather than being skipped silently.
9. Docs sync: add `RunEventType` to the enums table and an event-stream line (key, cap, TTL, id semantics) under "Jobs and Events" in `.agents/ctx/server-context.md`.

## Out of scope

- The SSE endpoint `GET /v1/runs/{id}/events` and keep-alive handling.
- Publishing from `run_graph` or mapping LangGraph `astream` chunks to event types.
- Payload schemas per event type (`data` stays a free-form JSON object).
- Consumer groups, acknowledgements and fan-out beyond plain `XREAD`.
- Persisting events to Postgres; Redis is losable by design.
- Per-run locks and the outbox relay.
- A safety TTL for streams of runs that never reach a terminal status (crashed workers); left to `cleanup` or a later PRD.

## Touches

`server/metis/core/events.py` (new), `server/tests/core/test_events.py` (new), `.agents/ctx/server-context.md`.

## Dependencies

None in Linear. Uses `REDIS_URL` from `core/config.py` (chore-core-config, done) and the Redis test setup from chore-arq-worker (done). Parent: SHIP-209.

## Test seam

One seam, the highest available: the public `publish` / `read` API in `core/events.py` against a real Redis (`TEST_REDIS_URL`, default `redis://localhost:6379/15`; skip when unreachable, as `tests/core/test_jobs.py` does). Tests assert only what a caller sees: returned ids, yielded `RunEvent`s, their order, timing of blocking reads, and the stream TTL via `TTL`. No assertions on internal helpers or raw field encoding. Prior art: `tests/core/test_jobs.py` (Redis fixture, flush per test, skip if unreachable).

Planned tests:

- Publish three events, read from the start: three `RunEvent`s in order with the ids `publish` returned.
- Read after the second id: only the third event.
- Blocking read on an empty tail returns when another task publishes, well before `block_ms`.
- Blocking read with no new events yields nothing after about `block_ms`.
- Publishing a terminal `run_status` sets the stream TTL to 24 hours or a little less; non-terminal events, including `run_status` `running`, leave no TTL.
- Publishing more than the cap keeps the stream near 5000 entries (approximate trim).
- A malformed entry written directly with `XADD` raises the domain error on read.

## Acceptance criteria

- [x] Events are read back in order with stable ids.
- [x] Reading after a given id returns only later events (needed for reconnect).
- [x] A blocking read returns when a new event arrives.
- [x] The stream gets a 24-hour TTL after the run ends.
- [x] Streams are capped with `MAXLEN ~ 5000`.
- [x] `server-context.md` lists `RunEventType` and the stream conventions.
- [x] `uv run ruff check`, `uv run mypy`, `uv run pytest` pass.

## Open questions

None. Resolved 2026-11-13:

1. Expiry is automatic: `publish` sets the 24-hour TTL when it emits a terminal `run_status` (`succeeded`, `failed`, `cancelled`). There is no `close` function.
2. No safety TTL before a run ends; deferred to `cleanup` or a later PRD.
3. Test seam confirmed: public `publish` / `read` against a real Redis, no fake Redis.

## Status

done
