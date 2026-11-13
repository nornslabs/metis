# PRD: chore-outbox-relay

Linear: SHIP-213 · https://linear.app/heimdallabs/issue/SHIP-213/073-transactional-outbox-and-relay-job

## Problem / Goal

The code standards say domain events go to the outbox in the same transaction as the change, and the `maintenance` queue already runs an `outbox_relay` job every 5 seconds. But `core.outbox` does not exist and `outbox_relay` is a no-op stub. A module that confirms a spec has no safe way to tell other modules about it. If it publishes after commit, a crash loses the event. If it publishes before commit, a rollback sends an event for a change that never happened.

Goal: a transactional outbox in `core/outbox.py`. A service writes a domain event into `core.outbox` inside its own transaction. The `outbox_relay` job reads unpublished events, hands each one to the handlers registered for its type, and marks it published. Delivery is at least once. Concurrent relays never deliver the same event twice. Failed events retry and stop after 10 attempts.

## User stories

1. As a module author, I want `add_event(session, event)`, so that I can record a domain event in the same transaction as my data change.
2. As a module author, I want `add_event` to only insert and never commit or flush-and-commit, so that my service keeps full control of the transaction.
3. As a module author, I want an event written in a transaction that rolls back to disappear, so that other modules never react to a change that did not happen.
4. As a module author, I want a typed `DomainEvent` envelope (`id`, `workspace_id`, `type`, `payload`, `created_at`), so that producers and handlers agree on one shape.
5. As a module author, I want domain event types defined once as an enum, so that a typo in `"SpecConfirmed"` fails at type-check time, not silently in production.
6. As a module author, I want each event to get a UUIDv7 id at creation, so that the id is time-ordered and can key idempotent handling.
7. As a handler author, I want an `@on_event(DomainEventType.SPEC_CONFIRMED)` decorator, so that I can subscribe to an event type without editing the relay.
8. As a handler author, I want several handlers on one event type, so that more than one module can react to the same event.
9. As a handler author, I want my handler to receive the full `DomainEvent` including its id, so that I can make it idempotent by keying on the event id.
10. As a handler author, I want a clear rule that delivery is at least once, so that I know I must tolerate seeing the same event again.
11. As an operator, I want the relay to process events in creation order, so that downstream effects happen in a sensible order.
12. As an operator, I want the relay to take at most 100 events per batch, so that one run stays short and memory stays bounded.
13. As an operator, I want two relays running at the same time to never deliver the same event, so that scaling or overlapping runs cannot double-send.
14. As an operator, I want a relay that hits a locked row to skip it, not wait, so that relays never block each other.
15. As an operator, I want an event whose handler raises to stay unpublished with its `attempts` increased, so that the next relay run retries it.
16. As an operator, I want one failing event not to stop the rest of its batch, so that a single bad event cannot stall the outbox.
17. As an operator, I want an event to stop retrying after 10 failed attempts with an error log, so that a poisoned event does not retry forever.
18. As an operator, I want the error log to carry the event id, type, workspace id and attempts, so that I can find and replay the event by hand.
19. As an operator, I want an event type with no registered handler to be marked published, so that unhandled events do not pile up as unpublished rows.
20. As an operator, I want a partial index on unpublished rows, so that the relay query stays fast as the published history grows.
21. As an operator, I want the scheduler to enqueue the relay every 5 seconds without duplicates, so that delivery latency stays low and the queue does not flood (already built in SHIP-211).
22. As a developer, I want the relay logic callable outside Arq, so that tests and scripts can drive one relay pass directly.
23. As a developer, I want tests to use an isolated handler registry, so that test handlers never leak into the real one.

## Requirements

1. **Migration** `0002_core_outbox`: table `core.outbox` with
   - `id uuid primary key` (UUIDv7, generated in Python by `DomainEvent`),
   - `workspace_id uuid not null`,
   - `type text not null`,
   - `payload jsonb not null`,
   - `created_at timestamptz not null default now()`,
   - `published_at timestamptz null`,
   - `attempts int not null default 0`;
   - a partial index on `(created_at, id) WHERE published_at IS NULL`.
   No RLS on this table (decided, see Open questions). Downgrade drops the table.
2. **Model**: a SQLAlchemy model for `core.outbox` in `core/outbox.py` (core owns it; it is not a module table).
3. **Event types**: `DomainEventType` `StrEnum` in `core/outbox.py` with exactly `IdeaSubmitted`, `ScoreComputed`, `SpecConfirmed`, `PlanReady`, `ExportFinished`, `MarketSignalDetected` (the list in `server-context.md`; the issue lists the first five).
4. **Envelope**: `DomainEvent` Pydantic v2 model: `id: UUID` (defaults to a new UUIDv7), `workspace_id: UUID`, `type: DomainEventType`, `payload: dict[str, Any]`, `created_at: datetime` (UTC). Payload schemas per type are out of scope.
5. **Write**: `add_event(session: AsyncSession, event: DomainEvent) -> None` (a plain function; it does no I/O) adds one row to the session. It never commits, flushes-and-commits or opens its own transaction.
6. **Registry**: `on_event(type)` decorator registers an `async def handler(event: DomainEvent) -> None` on a module-level registry. Many handlers per type are allowed. The registry is a small class so tests can pass their own instance.
7. **Relay**: `relay_once(sessionmaker, *, registry=default, batch_size=100) -> RelayResult` runs one pass in one transaction:
   - `SELECT … FROM core.outbox WHERE published_at IS NULL AND attempts < 10 ORDER BY created_at, id LIMIT 100 FOR UPDATE SKIP LOCKED`;
   - for each row, call every handler registered for its type, in registration order (handlers use their own sessions, so no savepoint is needed);
   - all handlers succeed (or none registered) → set `published_at = now()`;
   - the row fails to decode (for example an unknown type) or any handler raises → increment `attempts`; below 10 log `outbox.event_failed` at warning level, at 10 log `outbox.event_dead` at error level instead, with event id, type, workspace id and attempts;
   - commit once at the end; row locks are held until then.
   `RelayResult` reports counts of published, failed and dead events.
8. **Constants**: `RELAY_BATCH_SIZE = 100`, `MAX_ATTEMPTS = 10` named in `core/outbox.py`.
9. **Job**: replace the `outbox_relay` stub in `entrypoints/worker.py` with a call to `relay_once` using the core sessionmaker. It stays on the `maintenance` queue (`max_jobs=1`). The scheduler stays as built in SHIP-211 (enqueue every 5 s with a per-window `job_id`).
10. **Handler sessions**: a handler opens its own session if it writes; it is not handed the relay's session. Handlers use other modules only through their `service.py`.
11. **UUIDv7**: Python 3.12 has no `uuid.uuid7` and Postgres 16 has no `uuidv7()`. Add `uuid7() -> UUID` in `core/ids.py`: a small RFC 9562 generator (48-bit Unix ms timestamp, version 7, variant bits, random rest), with a unit test for version, variant and time ordering. No new dependency.
12. **Docs sync**: in `.agents/ctx/server-context.md`, add `DomainEventType` to the enums table and expand the domain events line under "Jobs and Events" with the `add_event` / `on_event` / relay contract (at-least-once, idempotent handlers keyed on event id, batch 100, `SKIP LOCKED`, 10 attempts).

## Out of scope

- Emitting real domain events from modules (ideas, scoring, planning); each module adds its own `add_event` calls.
- Real handlers; this PRD ships only the registry.
- A per-handler delivery ledger or a framework-level dedupe table; handlers own their idempotency.
- Backoff between retries (a failed event retries on the next 5-second run).
- A replay or dead-letter admin tool for events that hit 10 attempts.
- Pruning old published rows (left to `cleanup`).
- Publishing domain events to Redis or SSE.
- Changes to the scheduler cadence or queue routing.

## Touches

`server/metis/core/outbox.py` (new), `server/migrations/versions/0002_core_outbox.py` (new), `server/metis/core/ids.py` (new), `server/metis/core/models.py` (naming convention fixed to %-format strings, required for the first model on `Base`; `generate_uuid` now UUIDv7), `server/metis/entrypoints/worker.py`, `server/tests/core/test_jobs.py` (maintenance worker test stubs `relay_once` and asserts success), `.agents/ctx/architecture.md` (`core.outbox` exception), `server/tests/core/test_outbox.py` (new), `server/tests/core/test_ids.py` (new), `.agents/ctx/server-context.md`.

## Dependencies

- `chore-arq-worker` (SHIP-211) — done. Provides the `maintenance` worker, the `outbox_relay` stub and the 5-second scheduler tick.
- `chore-migrations-rls` — done. Provides the `core` schema and Alembic setup.
- Parent: SHIP-209.

## Test seam

One seam, the highest available: the public API of `core/outbox.py` (`add_event`, `on_event` with a test registry, `relay_once`) against a real Postgres with the migration applied. Tests use `TEST_DATABASE_URL` (default `postgresql+asyncpg://postgres:postgres@localhost:5432/metis`), skip when Postgres is unreachable (as `tests/core/test_jobs.py` does for Redis), and truncate `core.outbox` per test. Tests assert only what a caller sees: handler calls, `RelayResult` counts, and the row's `published_at` / `attempts`. The Arq job wrapper is a one-line call and is not tested through Arq. Prior art: `tests/core/test_jobs.py`, `tests/core/test_events.py` (real backing service, skip if unreachable, clean per test).

Planned tests:

- `add_event` then commit → one relay pass calls the handler once with the same event; row has `published_at`.
- `add_event` then rollback → relay pass calls no handler; table is empty.
- Two `relay_once` calls run in parallel on 150 events (handlers sleep briefly) → every event is delivered exactly once across both.
- A handler that raises → event stays unpublished with `attempts = 1`; the next pass retries it.
- One failing event in a batch → the other events in the batch are still published.
- An event that fails 10 times → no further delivery; `outbox.event_dead` is logged.
- An event type with no handlers → marked published.
- Batch limit → 150 events need two passes; the first publishes 100, in creation order.

## Acceptance criteria

- [x] An event written in a rolled-back transaction is never delivered.
- [x] Concurrent relays never double-deliver.
- [x] Failed deliveries retry and stop after 10 attempts with an error log.
- [x] `outbox_relay` on the `maintenance` queue runs `relay_once`; the scheduler enqueues it every 5 seconds.
- [x] `alembic upgrade head` and `downgrade -1` work for `0002_core_outbox`.
- [x] `server-context.md` lists `DomainEventType` and the outbox contract.
- [x] `uv run ruff check`, `uv run mypy`, `uv run pytest` pass.

## Open questions

None. Resolved 2026-11-13:

1. No RLS on `core.outbox`: a core system table, never exposed by an API; `workspace_id` is kept for handler context and logs.
2. UUIDv7 comes from a small hand-written helper in `core` (no new dependency).
3. The event is the retry unit: if any handler raises, the whole event retries; handlers must be idempotent.
4. Test seam confirmed: public `core/outbox.py` API against a real Postgres, no Arq-level test.

## Status

done
