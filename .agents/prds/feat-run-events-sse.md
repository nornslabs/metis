# PRD: feat-run-events-sse

Linear: SHIP-234 · https://linear.app/heimdallabs/issue/SHIP-234/163-sse-run-events-endpoint-with-reconnect

Milestone: M2 — Ideas and agent run engine. Branch: `feat/run-events-sse`. Parent: SHIP-225 (run engine). Blocked by SHIP-232 (done) and SHIP-263 (done).

## Problem / Goal

The worker publishes every run event to a Redis stream (`core.events`), and the Runs API (SHIP-232) starts, resumes and cancels runs. Nothing yet lets the browser watch a run live. The web app (`useRunEvents`) needs a Server-Sent Events endpoint that streams a run's events, survives a dropped connection without missing or repeating an event, and ends cleanly when the run ends.

Goal: `GET /v1/runs/{run_id}/events` streaming `text/event-stream`, resumable with `Last-Event-ID`.

## User stories

1. As a workspace member, I want to open a live stream of a run's events, so that I see progress without refreshing.
2. As a user, I want each event to carry its type and JSON data, so that the page can render node starts, tokens, tool calls, questions and status changes.
3. As a user opening the stream on a run that already emitted events, I want to receive them from the start, so that the page shows the whole run.
4. As a user whose connection dropped, I want the browser's automatic reconnect (`Last-Event-ID`) to continue exactly after the last event I saw, so that I miss nothing and see nothing twice.
5. As a developer, I want `?after=<id>` as an alternative to the header, so that I can resume with a plain `curl` or a client that cannot set headers.
6. As a user, I want the stream to close by itself after the run reaches `succeeded`, `failed` or `cancelled`, so that the browser stops reconnecting and the server frees the connection.
7. As a user, I want the terminal `run_status` event delivered before the stream closes, so that the page learns how the run ended.
8. As a user, I want a quiet run to keep its connection open, so that proxies and browsers do not time it out.
9. As a user, I want a `: ping` comment about every 15 s while no event arrives, so that idle connections stay alive.
10. As an operator, I want the server to stop reading Redis when the client disconnects, so that closed tabs leave no work behind.
11. As a user, I want a run of another workspace (or one that does not exist) to be a 404, so that I cannot probe other tenants.
12. As a user, I want an unsigned request to be 401, so that streams need a session.
13. As a user, I want a run of an archived idea to be a 404, like every other run route.
14. As a user, I want a malformed `Last-Event-ID` or `after` value rejected with 422 before the stream opens, so that a bad id never reaches Redis.
15. As a user behind a reverse proxy, I want `Cache-Control: no-cache` and `X-Accel-Buffering: no`, so that events are not cached or held back.
16. As a user opening the stream on a run that finished and whose stream already expired (24 h), I want a clear, finished answer rather than an endless wait, so that the page does not hang.
17. As a web developer, I want the browser's `EventSource` with credentials to authenticate with the session cookie, so that no extra token round trip is needed.
18. As an operator, I want a stream entry that cannot be decoded to end the stream with a logged error, not to crash the worker or hide later events silently, so that one bad entry is visible.
19. As a developer, I want the route in the route-table auth test, so that a route that forgets auth fails CI.
20. As a web developer, I want the OpenAPI schema to list the route as `text/event-stream`, so that the client documents it.

## Requirements

1. **Route.** `GET /v1/runs/{run_id}/events?workspace_id&after` in module `ideas` (new `controller/run_events.py`, registered beside `runs.py`). Auth: session cookie via `current_workspace`, which for this route also reads `?workspace_id=` because `EventSource` cannot set `X-Workspace-Id`; it is a `GET`, so no `X-Metis-Client` header (`EventSource` cannot send one). Response `200`, `Content-Type: text/event-stream`.
2. **Check before streaming.** Before the first byte, open a session, read the run with `service.workflow_runs.get_run_view` (unknown, other-workspace or archived-idea run → `404 run.not_found`), then release the DB session. The stream itself holds no database connection.
3. **Start position.** `Last-Event-ID` header, else `?after=`, else the stream start (`events.STREAM_START_ID`). If both are given the header wins. A value that is not a Redis stream id (`<ms>-<seq>`, digits only) → `422 common.validation_failed` before streaming.
4. **Loop.** Repeatedly call `events.read(run_id, after_id, block_ms=15000)` and advance `after_id` to the last id yielded. The stream opens its own Redis client (the shared `RedisDep` client has a 0.5 s socket timeout, shorter than a blocking read) and closes it when the stream ends.
5. **Frames.** Each event is `id: <redis id>`, `event: <type>`, `data: <json>` followed by a blank line. `data` is the JSON object `{run_id, type, data, ts}` (the decoded event). Retry-interval hint `retry: 3000` is sent once at the start.
6. **Heartbeat.** When a read returns no events (the 15 s block elapsed), send `: ping`. This is the only heartbeat; its period is the read block.
7. **Termination.** After yielding a `run_status` event whose status is in `events.TERMINAL_RUN_STATUSES`, end the stream cleanly. The terminal event is sent first. If the start position is itself a terminal `run_status` entry, close at once with no frames. A client that disconnects stops the loop at the next await (no further `XREAD`).
8. **Headers.** `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`.
9. **Finished run with no stream.** If the run is already `succeeded`, `failed` or `cancelled` and its stream has no entries (expired, or none ever published), send one synthetic `run_status` frame from the database row (no `id:`, so the client does not resume from it) and close (see Resolved).
10. **Decode failure.** `MalformedEventError` while streaming: log `run.event_malformed` with the run id and entry id, send an `event: error` frame with code `run.event_malformed`, close the stream.
11. **Library.** `sse-starlette` is not a dependency, so a plain `StreamingResponse` with a small frame formatter in `helpers/sse.py`.
12. **Module boundaries.** The controller reads events only through `core.events` and the run only through `service`. No repo or model imports; the agent graph is untouched.

## Out of scope

- `POST /v1/runs/{id}/events/token` and `?token=` auth (the issue's step 2): superseded by server-owned sessions; `EventSource` with credentials sends the cookie. See Decisions.
- Web `useRunEvents` hook and any UI (SHIP-219 and later).
- Changing event types, payloads or retention in `core.events` (SHIP-212).
- Replaying beyond the stream cap (`MAXLEN ~ 5000`) or the 24 h TTL.
- A workspace-wide or idea-wide event stream.
- Rate limiting or a per-user cap on open streams.

## Touches

- `server/metis/modules/ideas/controller/` (new `run_events.py`; router registration).
- `server/metis/modules/ideas/helpers/` (SSE frame formatter, event-id validation) if `sse-starlette` is not used.
- `server/metis/modules/identity/deps.py` (new `StreamWorkspaceDep`: header or `?workspace_id=`).
- `server/tests/modules/ideas/` (new `test_run_events_api.py`), route-table auth test.
- `.agents/ctx/server-context.md` (route and SSE conventions), `.agents/progress-tracker.md`.

## Dependencies

- `feat-runs-api` (SHIP-232): done.
- `feat-auth-sessions` (SHIP-264) / `feat-auth-google` (SHIP-265): done.
- `chore-redis-streams` (SHIP-212): done.

## Testing

Seam: the HTTP seam, as in `test_runs_api.py`: a real FastAPI app over `httpx` with the session-cookie sign-in helper, real Postgres (`metis_app`) and real Redis; events are published with `core.events.publish`. One seam, no mocks of the event bus. Tests assert what a client sees on the wire.

- Replay: events published before connecting arrive in order with their Redis ids.
- Resume: connecting with `Last-Event-ID: <id of event 2>` yields events 3.. only; `?after=` does the same; the header wins when both are set.
- Live: an event published after the connection opens is delivered.
- Heartbeat: with `block_ms` shortened through a module constant patched in the test, an idle stream emits `: ping`.
- Terminal: after a terminal `run_status` the response ends; the terminal frame is the last frame. Covers `succeeded`, `failed`, `cancelled`.
- Disconnect: closing the frame generator (what Starlette does on disconnect) stops the reader. `httpx.ASGITransport` buffers a response until it ends, so this is checked on `stream_frames` directly.
- Isolation: a run of another workspace and an unknown run id → 404 `run.not_found`; no cookie → 401.
- Validation: malformed `Last-Event-ID` / `after` → 422 before any bytes.
- Headers: content type, `Cache-Control`, `X-Accel-Buffering`.
- Expired stream: terminal run with no entries → one synthetic `run_status` frame, then close.
- Malformed entry: an undecodable entry ends the stream with an `error` frame.
- Workspace: `?workspace_id=` of a non-personal workspace the caller belongs to finds the run; a workspace the caller is not in → 403 (`auth.forbidden`, as with the header).
- Resume after terminal: `Last-Event-ID` equal to the terminal event's id closes with no frames.
- Route-table auth test lists the new route.

## Acceptance criteria

- [x] Reconnecting with `Last-Event-ID` resumes exactly after that event (no gap, no duplicate).
- [x] The stream ends cleanly after a terminal `run_status`, and when the client disconnects.
- [x] Frames are `id` / `event` / `data`; `: ping` is sent about every 15 s when idle; headers are set.
- [x] A run of another workspace, an unknown run or an archived idea's run is 404; no session is 401.
- [x] The route holds no DB connection while streaming.
- [x] Tests above pass; `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run lint-imports` pass.
- [x] `server-context.md` and the tracker are updated.

## Decisions (proposed, from `.agents/ctx/`)

- No stream token. `server-context.md` already states "session cookie via `EventSource` with credentials, no stream token"; the issue's `?token=` and `POST /v1/runs/{id}/events/token` predate server-owned sessions (SHIP-263). The JWT the issue mentions no longer exists.
- Stream requests may name the workspace with `?workspace_id=` (the header still wins).
- `data` is the whole decoded event envelope, not only `data`, so a client handler gets `run_id` and `ts` with the payload.

## Open questions

None open.

## Resolved

- Workspace on a stream request: the route accepts `?workspace_id=` (same membership check as `X-Workspace-Id`; the header wins if both are sent) (user, 2026-11-16).
- A finished run whose stream expired gets one synthetic `run_status` frame from the database, then the stream closes (user, 2026-11-16).
- Resuming with a `Last-Event-ID` that is the terminal event closes the stream at once with no frames (user, 2026-11-16).

## Status

done
