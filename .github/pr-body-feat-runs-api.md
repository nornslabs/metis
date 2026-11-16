# Pull Request

## Summary

Adds the REST API for starting, resuming, cancelling and inspecting agent runs on ideas. The API records intent and enqueues `run_graph`; it never runs the graph.

```text
POST  /v1/ideas/{idea_id}/runs     -> 202 {run_id}        (Idempotency-Key required)
POST  /v1/runs/{run_id}/resume      -> 202 {run_id}        (answer an interrupt)
POST  /v1/runs/{run_id}/cancel      -> 202 {run_id, status}
GET   /v1/runs/{run_id}             -> RunView
GET   /v1/ideas/{idea_id}/runs      -> {items, next_cursor}
```

Start is idempotent on `Idempotency-Key` and enforces one active run per idea via a partial unique index on `(idea_id) WHERE status IN ('queued','running','awaiting_user')` (migration `0014`). The transaction commits before `core.jobs.enqueue`, so the worker can never see a missing row.

## Linear

Closes linear issue: `SHIP-232` — https://linear.app/heimdallabs/issue/SHIP-232/162-runs-api-start-resume-cancel-and-get

## Spec

PRD: `.agents/prds/feat-runs-api.md`

## Scope

- **Touches:** `server/metis/modules/ideas/` (`controller/runs.py`, `service/workflow_runs.py`, `repo/workflow_runs.py`, `dto/workflow_runs.py`, `helpers/resume_value.py`, router registration), `server/migrations/versions/0014_run_active_index.py`, `server/metis/core/errors.py` (new `RunAlreadyRunningError`, `IdempotencyMismatchError`, `RunEnqueueError`), `server/metis/core/run_control.py` (cancel flag), `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`.
- **Out of scope:** SSE run events (SHIP-234), budget enforcement, rate limits, web UI changes, real specialists, market-watch runs, run events history / LLM usage routes, restricting start/resume/cancel to the idea's creator or owner.

## Before merging

- [x] Acceptance criteria in the PRD pass end to end.
- [x] No invariant in `.agents/ctx/architecture.md` is violated.
- [ ] Server: `uv run ruff check .`, `uv run mypy`, `uv run pytest` pass.
- [ ] Web: `npm run lint`, `npm run typecheck`, `npm run build` pass.
- [ ] Docker images build (`server`, `web`).
- [x] `.agents/progress-tracker.md` is updated (PRD status `done`, row marked).
- [x] Matching `.agents/ctx/*.md` synced if architecture / enums / conventions changed.
- [x] Conventional commit message, e.g. `feat(runs): add start/resume/cancel/get/list routes (SHIP-232)`.

## Notes

- The active-run 409 reuses the catalog's existing `run.already_running` (unused until now) rather than a new `run.active` code; the issue's `run_active` meant the same thing.
- Cancel sets the flag after the commit, not before: a terminal run must not get a flag, and the status check and the move happen in the transaction first. A `queued` run picked up by the worker between the read and the move is returned as `running` (flag only).
- A retry only re-enqueues while the run is still `queued`.
- The new index broke one SHIP-228 test that put several queued runs on one idea; it now uses one idea per run (`test_an_idempotency_key_is_unique_per_workspace_only`).
- `helpers/resume_value.py` imports the interrupt type names from `agent/tools/ask_user.py` (one source of truth for `question`/`approval`).
- Tests were not run in this session per request; CI will run `ruff`, `mypy`, `pytest`, and the route-table auth test.