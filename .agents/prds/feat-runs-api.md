# PRD: feat-runs-api

Linear: SHIP-232 · https://linear.app/heimdallabs/issue/SHIP-232/162-runs-api-start-resume-cancel-and-get

Milestone: M2 — Ideas and agent run engine. Branch: `feat/runs-api`. Parent: SHIP-225 (run engine). Blocked by SHIP-228 (done). Blocks SHIP-234 (SSE run events).

## Problem / Goal

Runs exist in the database and the worker can drive them (SHIP-228), but nothing outside the worker can start, answer, stop or inspect one. The web app needs REST endpoints for that. The API only records intent and enqueues a job; it never runs the graph.

Goal: routes to start a run on an idea (idempotently, one active run per idea), resume a run that waits for the user, cancel a run, read one run and list an idea's runs.

## User stories

1. As a workspace member, I want to start a run on an idea, so that Metis begins working on it.
2. As a user, I want the start call to answer `202 {run_id}` at once, so that the page does not wait for the graph.
3. As a user, I want a double click or a network retry with the same `Idempotency-Key` to create one run, so that I never pay for two.
4. As a user, I want the retry to return the same `run_id` with the same `202`, so that the client needs no special case.
5. As a user, I want a start refused with `409 run_active` while the idea has a `queued`, `running` or `awaiting_user` run, so that two runs never fight over one idea.
6. As a user, I want a start on an unknown, archived or other-workspace idea to be a 404, so that I cannot probe other tenants.
7. As a user, I want the job enqueued only after the run row is committed, so that the worker never looks for a run that does not exist yet.
8. As a user, I want to answer a run's question with `POST /v1/runs/{id}/resume`, so that the interview continues.
9. As a user, I want the same route to carry my approve/reject decision for an approval, so that external writes wait for me.
10. As a user, I want a resume value of the wrong shape for the pending interrupt (text for an approval, a decision for a question) rejected with 422, so that a bad answer never reaches the graph.
11. As a user, I want a resume on a run that is not `awaiting_user` rejected with 409, so that a stale answer cannot disturb a running run.
12. As a user, I want a double-clicked resume to enqueue one job, so that the answer is applied once.
13. As a user, I want to cancel a run, so that I stop spending on work I no longer want.
14. As a user, I want a `queued` or `awaiting_user` run to become `cancelled` right away, so that I see it stop without waiting for a worker.
15. As a user, I want a `running` run to stop at its next step boundary after I cancel, so that a long run ends soon without being killed mid-step.
16. As a user, I want cancel on a finished run to be refused with 409, so that I am not told a done run was stopped.
17. As a user, I want to read a run: its status, the idea's stage, the pending question, and the error if it failed, so that the page can show where it is after a reload.
18. As a user, I want a failed run's error to be a stable code and message, so that the page can explain it without raw exception text.
19. As a user, I want to list an idea's runs, newest first, paged with a cursor, so that I can see its history.
20. As a user, I want the list to carry no archived-idea or other-workspace runs, so that tenants stay isolated.
21. As a user, I want every mutation to need `X-Metis-Client: web` and a session, like all other routes, so that cross-site requests cannot start runs.
22. As an operator, I want RLS to hide runs of other workspaces on every route, so that a missing check in code cannot leak data.
23. As an operator, I want a stuck enqueue (Redis down after commit) to fail the request with a clear error and leave a `queued` row I can see, so that nothing is silently lost.
24. As a developer, I want the routes in the route-table auth test, so that a route that forgets auth fails CI.
25. As a web developer, I want the OpenAPI schema to describe the run routes, so that the client can be generated.

## Requirements

1. **Routes** (module `ideas`, new `controller/runs.py`, all on `current_workspace`; mutations need `X-Metis-Client: web`):
   - `POST /v1/ideas/{idea_id}/runs`, header `Idempotency-Key` (required, 1–255 printable characters; missing or bad → 422), no body → `202 {run_id}`.
   - `POST /v1/runs/{run_id}/resume`, body `{value}` → `202 {run_id}`.
   - `POST /v1/runs/{run_id}/cancel` → `202 {run_id, status}`.
   - `GET /v1/runs/{run_id}` → the run (see Run view).
   - `GET /v1/ideas/{idea_id}/runs?cursor&limit` → `{items, next_cursor}`, newest first, default 20, max 100.
2. **Start.** In one transaction: look up the idea (archived/unknown → `idea.not_found`), look up a run with this idempotency key in the workspace; found → return it (no new row, no enqueue-side change beyond a safe re-enqueue, see below). Not found → reject with `409 run.active` when the idea already has a `queued`, `running` or `awaiting_user` run, else `create_run` with the key. The one-active-run rule is enforced by a partial unique index on `(idea_id) WHERE status IN ('queued','running','awaiting_user')` so a race lands as the same 409 (migration `0014`), not only by a read check. A concurrent double submit with the same key resolves through the existing `(workspace_id, idempotency_key)` unique constraint: the loser re-reads and returns the winner's run.
3. **Enqueue after commit.** The handler commits the transaction before calling `core.jobs.enqueue("run_graph", run_id=..., workspace_id=..., job_id=run_id)`, so the worker can never see a missing row. An idempotent retry also calls `enqueue` with the same `job_id`, which Arq dedupes; this repairs a first call that committed but failed to enqueue. If `enqueue` raises, the request fails with a `503`-class domain error and the `queued` row stays (a retry with the same key re-enqueues it).
4. **Resume.** Run must be `awaiting_user`, else `409 run.invalid_state`. `value` is validated against `pending_interrupt.type`: `question` → non-empty text (trimmed, max 10,000 characters); `approval` → a boolean decision. Wrong shape → 422. Enqueues `run_graph(run_id=..., workspace_id=..., resume=value, job_id=<run_id>:resume:<run version>)`. The resume job id includes the run's `version`, so a double submit for the same pause enqueues once and a later pause gets a fresh id. The row is not changed by the API; the worker moves it to `running`.
5. **Cancel.** Sets `cancel:{run_id}` (TTL 24 h) first. `queued` or `awaiting_user` → `mark_cancelled` in the same transaction and publish `run_status: cancelled` after commit (a worker job that still starts finds a terminal run and returns). `running` → only the flag is set; the worker ends the run at the next step boundary; the response status is `running`. Terminal run → `409 run.invalid_state`. Cancel is idempotent on a run that is already `cancelled`: returns `202` with status `cancelled`.
6. **Run view** (DTO): `id`, `idea_id`, `status`, `stage` (the idea's current stage), `pending_interrupt` (only while `awaiting_user`, else `null`), `error` (`{code, message}` or `null`), `started_at`, `finished_at`, `created_at`, `version`. `idempotency_key`, `workspace_id` and `kind` are not exposed. Page: `{items: [RunView], next_cursor}`.
7. **List** is keyset-paged on `(created_at, id)` with an opaque cursor, reusing the ideas cursor helper; an unknown idea → 404.
8. **Service additions** (`service/workflow_runs.py`, caller's session, never commit, scoped by workspace id): `start_run`, `get_run_view`, `list_runs`, `resume_run` (validates, returns the run and the job id inputs), `cancel_run`. The controller owns commit and enqueue ordering because the service must not commit.
9. **Errors** (catalog in `core/errors.py` and `server-context.md`): new `RunActiveError` (`run.active`, 409); new `RunEnqueueError` (`run.enqueue_failed`, 503); new `IdempotencyMismatchError` (`run.idempotency_mismatch`, 409); reuse `RunNotFoundError` (404), `IllegalRunTransition` (`run.invalid_state`, 409), `IdeaNotFoundError`, `InvalidInputError` (422). All RFC 7807.
10. **Docs.** `server-context.md` (routes, errors, resume value shapes, job id scheme, partial unique index), `architecture.md` (run flow: API commits then enqueues), tracker. Notion LLD sync follows.

## Out of scope

- The SSE endpoint and `Last-Event-ID` reconnect (SHIP-234).
- Budget enforcement (SHIP-237) and a per-user run rate limit.
- Moving `ideas.stage` or changing graph behaviour; real specialists.
- Market-watch runs (`stage=watch`).
- A route to read a run's events history or its LLM usage.
- Web UI changes.
- Restricting start/resume/cancel to the idea's creator or owner: any workspace member may act (as with reading); revisit if the product needs it.

## Touches

`server/metis/modules/ideas/` (`controller/runs.py`, `service/workflow_runs.py`, `repo/workflow_runs.py`, `dto/workflow_runs.py`, `helpers/` for resume validation, router registration, `__init__.py` exports), `server/migrations/versions/` (new `0014` partial unique index), `server/metis/core/errors.py`, `server/metis/core/run_control.py` (set the cancel flag), `server/metis/core/events.py` (publish only), `server/tests/modules/ideas/`, `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`, `.agents/progress-tracker.md`.

## Testing Decisions

- **Seam:** the HTTP API through the test client with a session cookie, real Postgres as `metis_app` and real Redis; `core.jobs.enqueue` replaced by a recording fake (the job itself is covered by SHIP-228). A good test asserts what the client and the queue see: status codes, response bodies, the run row, the enqueued job name/arguments/job id, the `cancel:` key, the published `run_status` event. It does not look at service internals.
- Tests planned:
  - Start: `202 {run_id}`, row `queued`, one job enqueued with `workspace_id` and `job_id=run_id`; the row is committed before the enqueue (assert from the fake, which reads the row on its own connection).
  - Idempotency: same key twice → same `run_id`, one row; concurrent double submit → one row; same key, different idea → `409 run.idempotency_mismatch`; missing key → 422.
  - Active-run conflict: `queued`, `running` and `awaiting_user` each give `409 run.active`; a terminal run does not block; the partial unique index holds under a concurrent start.
  - Resume: wrong status → 409; question with text → job enqueued with `resume`; approval with boolean → enqueued; wrong shape → 422; double submit → one job id.
  - Cancel: `queued` and `awaiting_user` → `cancelled` at once with the event and the flag; `running` → flag only, status unchanged; terminal → 409; already `cancelled` → 202.
  - Get and list: view fields (no key, no workspace id), `stage` from the idea, `pending_interrupt` only while awaiting, paging with cursor, order, unknown idea/run → 404.
  - RLS and auth: a run in another workspace is 404 on every route; no cookie → 401; mutation without `X-Metis-Client` → 403; routes appear in the route-table auth test.
  - Enqueue failure: the fake raises → 503 `run.enqueue_failed`, row stays `queued`, a retry with the same key enqueues it.
  - Migration `0014` up/down.
- **Prior art:** `tests/modules/ideas/` (HTTP-seam idea routes, `idea_helpers.py`, run service tests), the session-cookie sign-in helper from SHIP-264/267, the route-table test, `tests/agent/llm_helpers.py` `make_run`.
- `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run lint-imports` pass.

## Dependencies

- `feat-run-graph-job` (SHIP-228): done.
- `feat-ideas-crud` (SHIP-218): done.
- Blocks: SHIP-234 (SSE run events).

## Acceptance criteria

- [x] `POST /v1/ideas/{id}/runs` creates a `queued` run, enqueues `run_graph` after commit and returns `202 {run_id}`.
- [x] Double submit with the same `Idempotency-Key` creates one run and returns the same `run_id`.
- [x] A second run on an idea with a `queued`, `running` or `awaiting_user` run is `409 run.active`, including under a race.
- [x] `POST /v1/runs/{id}/resume` works only on `awaiting_user` (409 otherwise), validates `value` against the pending interrupt type (422 otherwise) and enqueues `run_graph` with `resume`.
- [x] `POST /v1/runs/{id}/cancel` sets the flag; `queued` / `awaiting_user` runs are `cancelled` at once; terminal runs are 409.
- [x] `GET /v1/runs/{id}` and `GET /v1/ideas/{id}/runs` return the run view and `{items, next_cursor}`.
- [x] All routes follow `server-context.md` conventions (202, `{items, next_cursor}`, RFC 7807) and are workspace-isolated by RLS.
- [x] Tests above pass; `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run lint-imports` pass.
- [x] `server-context.md`, `architecture.md` and the tracker are updated.

## Open questions

None open.

## Resolved

- Same `Idempotency-Key` on a different idea → `409 run.idempotency_mismatch` (new error); the existing run is not returned (user, 2026-11-16).
- Approval resume value is a boolean: `{value: true|false}`; question resume is non-empty text (user, 2026-11-16).
- `stage` in the run view is the idea's current stage, read live; no new column (user, 2026-11-16).
- Cancel on a `running` run returns `202` with `status: running`; the worker finishes the cancel (user, 2026-11-16).

## Built differently from the wording above, on purpose

- The active-run 409 reuses the catalog's existing `run.already_running` (unused until now) instead of a new `run.active`; the issue's `run_active` meant the same thing.
- Cancel sets the flag after the commit (not before): a terminal run must not get a flag, and the status check and the move happen in the transaction first. A `queued` run that the worker picks up between the read and the move is returned as `running` (flag only).
- A retry only re-enqueues while the run is still `queued`.
- The new index broke one SHIP-228 test that put several queued runs on one idea; it now uses one idea per run (`test_an_idempotency_key_is_unique_per_workspace_only`).
- `helpers/resume_value.py` imports the interrupt type names from `agent/tools/ask_user.py` (one source of truth for `question`/`approval`).

## Status

done
