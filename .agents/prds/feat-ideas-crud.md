# PRD: feat-ideas-crud

Linear: SHIP-218 · https://linear.app/heimdallabs/issue/SHIP-218/13-ideas-module-and-api

Milestone: M2 — Ideas and agent run engine. Branch: `feat/ideas-crud`.

## Problem / Goal

A signed-in user can sign in and save keys, but cannot yet put an idea into Metis. Every later step (interview, research, scoring, spec, plan, export) hangs off an idea and its stage, so nothing else can start until ideas exist.

Goal: a new `modules/ideas` module that stores ideas in the `ideas` Postgres schema, tracks each idea's stage through a validated transition table, and exposes CRUD routes so a user can submit, list, read, edit and archive ideas in their workspace. Creating an idea records an `IdeaSubmitted` event in the outbox in the same transaction.

Starting runs, interview turns and specs are not part of this PRD. The `ideas` module will own them later; this PRD builds only the idea row, its stage and its routes.

## User stories

1. As a signed-in user, I want to submit an idea with a title and a description, so that Metis has something to research and score.
2. As a user, I want a too-short or too-long title or description rejected with a clear message, so that I fix it before it is saved.
3. As a user, I want a new idea to start at stage `intake`, so that I can see it has not been worked on yet.
4. As a user, I want to list my workspace's ideas, newest first, so that I find recent work quickly.
5. As a user, I want the list paged with a cursor, so that a long list loads fast and I can keep scrolling.
6. As a user, I want to open one idea by id, so that I see its full text, kind, stage and score.
7. As a user, I want to edit an idea's title, text and kind, so that I can correct or sharpen it.
8. As a user, I want an edit to fail with a conflict when someone changed the idea since I loaded it, so that I never silently overwrite their change.
9. As a user, I want to archive an idea, so that it leaves my list without being destroyed.
10. As a user, I want an archived idea to disappear from the list and from direct reads, so that archive feels like delete but is recoverable by an operator.
11. As a user, I want asking for an unknown or archived idea to return 404, so that the app shows "not found" and not an error.
12. As a user, I want an idea in another workspace to look like it does not exist, so that I cannot see or change other people's ideas.
13. As a workspace member, I want to see ideas my teammates created, so that the workspace shares one list.
14. As a member, I want only the idea's creator or a workspace owner to edit or archive it, so that teammates cannot change my ideas by accident.
15. As a user, I want a `kind` of `software` or `other` (or unset), so that later steps know whether to draft an HLD.
16. As a user, I want `current_score` empty until the idea is scored, so that I never see a made-up score.
17. As a user, I want a `version` on every idea that goes up on each edit, so that conflicts are detectable.
18. As a user, I want leading and trailing spaces trimmed from the title and text, so that padding does not count toward limits.
19. As a user, I want creating an idea to need the `X-Metis-Client` header like every other mutation, so that cross-site requests cannot create ideas.
20. As an agent graph (later), I want `transition(idea, to_stage)` to accept only legal moves, so that a run cannot put an idea in an impossible stage.
21. As an agent graph, I want an illegal move to raise `IllegalTransition` (409), so that bugs fail loudly and are not saved.
22. As the scoring and run engine (later), I want to react to `IdeaSubmitted` through the outbox, so that work starts without the idea service calling them.
23. As an operator, I want the event written in the same transaction as the idea, so that a rolled-back create leaves no event and a committed one is never lost.
24. As an operator, I want RLS on `ideas.ideas`, so that a missing `workspace_id` check in code cannot leak data.
25. As an operator, I want `metis_app` to have rights on the `ideas` schema and on tables added to it later, so that the api and workers do not hit "permission denied".
26. As an operator, I want `alembic downgrade` to drop the `ideas` table and revoke the `metis_app` grants cleanly, so that a rollback is possible.
27. As a developer, I want `ideas` to import other modules only through their public surface, with an import-linter contract, so that boundaries hold.
28. As a developer, I want the ideas routes in the route-table auth test, so that a route that forgets auth fails CI.
29. As a web developer, I want the OpenAPI schema to describe the idea routes, so that the client can be generated.

## Requirements

1. **Migration `0010_ideas`** (module-level SQL constants where a test replays them):
   - The `ideas` schema already exists (`0001_initial` creates every module schema), so the migration does not create or drop it. It grants `metis_app` `USAGE` on it plus default privileges for tables and sequences added later (as `0008_auth_schema` does for `auth`); tables get DML through those defaults. Downgrade drops the table and revokes the grants; the empty schema stays.
   - Table `ideas.ideas`: `id uuid pk`, `workspace_id uuid not null` (FK `identity.workspaces.id`, `ON DELETE CASCADE`), `created_by uuid not null` (FK `auth.users.id`), `title text not null`, `raw_text text not null`, `kind text null` (CHECK in `software`, `other`), `stage text not null default 'intake'` (CHECK in the nine `Stage` values), `current_score` (null), `version int not null default 1`, `archived_at timestamptz null`, `created_at`, `updated_at`.
   - Tenant RLS through the existing `enable_tenant_rls` helper. A list index on `(workspace_id, created_at desc, id desc) WHERE archived_at IS NULL`.
   - `kind` and `stage` are text + CHECK, as `members.role` and `provider_keys.kind` are.
2. **Module `modules/ideas/`** in the standard layers: `controller/ideas.py`, `service/ideas.py`, `repo/ideas.py`, `models/ideas.py` (`SCHEMA = "ideas"`), `dto/ideas.py`, `helpers/` for the transition table and cursor if module-only. Public surface in `__init__.py`: `router` and the domain types other modules need (`Idea`, `Stage`, `IdeaKind`, `transition`, `get_idea`). Nothing else.
3. **Service** (`service/ideas.py`; takes the caller's `AsyncSession`, never commits, sets no RLS of its own because `current_workspace` already did):
   - `create_idea(session, membership, data) -> Idea`: validates, inserts at stage `intake`, version 1, and calls `outbox.add_event` with `IdeaSubmitted` (payload: `idea_id`, `created_by`) in the same transaction.
   - `get_idea(session, workspace_id, idea_id) -> Idea`: unknown, archived or other-workspace → `idea.not_found` (404).
   - `list_ideas(session, workspace_id, cursor, limit) -> Page[Idea]`: newest first, archived excluded, keyset on `(created_at, id)`.
   - `update_idea(session, membership, idea_id, patch)`: patch carries the expected `version` and any of `title`, `raw_text`, `kind`. A stale version → `ConflictError` (409). A successful edit bumps `version` and `updated_at`. Stage is not editable here.
   - `archive_idea(session, membership, idea_id)`: sets `archived_at`; idempotent on an already archived idea is not offered (it is a 404, as the idea is hidden).
   - `transition(session, idea_id, to_stage) -> Idea`: checks the allowed-transitions map; an illegal move raises `IllegalTransition` (`idea.invalid_transition`, 409). A legal move bumps `version`. Not exposed over HTTP in this PRD.
   - Edit and archive allowed only to the idea's creator or a workspace `owner`; anyone else in the workspace → `PermissionDeniedError` (`idea.not_owner`, 403).
4. **Transition table**: one frozen mapping from `Stage` to the set of stages it may move to (see Open questions 1 for the proposed contents). Same stage → same stage is illegal.
5. **Routes** (`/v1/ideas`, all on `CurrentWorkspaceDep`):
   - `POST /v1/ideas` `{title, raw_text, kind?}` → `201 Idea`.
   - `GET /v1/ideas?cursor=&limit=` → `{items, next_cursor}`; default limit 20, max 100; `next_cursor` is an opaque string, `null` on the last page; a malformed cursor → 422.
   - `GET /v1/ideas/{id}` → `Idea`.
   - `PATCH /v1/ideas/{id}` `{version, title?, raw_text?, kind?}` → `Idea`, or 409.
   - `DELETE /v1/ideas/{id}` → `204` (soft archive).
   - `Idea` response: `id, workspace_id, created_by, title, raw_text, kind, stage, current_score, version, created_at, updated_at`. `archived_at` is not returned.
6. **Validation** at the DTO boundary: title 3–120 characters, `raw_text` 10–10,000 characters, both trimmed before counting (via `helpers.text.strip`); `kind` ∈ `software`, `other` or null. Invalid input → 422 through the existing validation error.
7. **Errors**: use `idea.not_found`, `idea.invalid_transition` and `idea.not_owner` from the existing catalog; add an `IllegalTransition` class (409, code `idea.invalid_transition`) and `IdeaNotFoundError` if `core/errors.py` has no exception class for them yet. Version mismatch uses the generic `ConflictError`.
8. **Wiring and boundaries**: `entrypoints/api.py` includes `ideas.router`. Add `metis.modules.ideas` to the import-linter layers contract above `identity` (`ideas → identity → auth`), and a contract that `ideas` uses only identity's and auth's public surface.
9. **Logging**: bind `idea_id` to the log context on routes that take an id. Log `idea.created` and `idea.archived` (ids only, never title or text).
10. **Docs** (Keeping Docs in Sync): `server-context.md` (module table row, ideas service and route contract, `ideas` schema grants, error table: `IllegalTransition`, the transition table), `architecture.md` (import chain `ideas → identity → auth`, ownership rule as built), the AGENTS.md tree if the layout line changes, and the Notion LLD ideas section.

## Implementation decisions

- **Archive is a column, not a stage.** `Stage` is fixed by `server-context.md` and has no `archived` value, so soft delete adds a nullable `archived_at` column. The issue's column list does not include it; this PRD adds it. Archived ideas are hidden everywhere (404), so no route needs an `include_archived` flag.
- **Access rule**: every workspace member reads; only the creator or a workspace owner edits and archives. This follows `architecture.md` ("only the owner or workspace admins mutate"), mapping "admin" to the existing `owner` role.
- **Keyset pagination** on `(created_at desc, id desc)`; the cursor is the base64url of the last row's `(created_at, id)`. Ids are UUIDv7, so the order is stable. Cursor encoding lives in a helper so later lists (runs, research items) can reuse it.
- **Optimistic concurrency** matches `PATCH /v1/settings`: the body carries `version`, a stale one is 409.
- **The service never commits and relies on `current_workspace` for RLS context**, like the other services; a repo query still filters by `workspace_id` so a missing context cannot widen a read.
- **`IdeaSubmitted` carries ids only** (`idea_id`, `created_by`); handlers read the idea through `ideas.get_idea`. No title or text in events or logs.
- **`transition` is service-level only.** The agent graph calls it later through the service; there is no stage-changing route in this PRD.
- **`current_score`** is a nullable integer 0–100 (CHECK), written only by the scoring module (SHIP-227), which may refine the type in its own migration.
- **Dependency note**: the issue is "blocked by JWT auth, workspace scoping and /me" (SHIP-216). That work is done and has since moved to session cookies (SHIP-264/265/267/268), so the dependency holds and the routes use `current_workspace`.

## Testing decisions

Good tests here check only what a client or operator can see: HTTP responses, rows in Postgres, and rows in the outbox. They do not check which file holds a function.

- **Seam 1 — HTTP (main seam)**, as in SHIP-264/265/267/217: `httpx` against the real app, real Postgres (as `metis_app`) and Redis, signed in through the shared `tests/helpers/auth.py` helpers. Covers:
  - create, read, edit, archive, list; validation bounds (title 2/3/120/121, text 9/10/10,000/10,001, whitespace trimming);
  - pagination: pages of a set size, no gaps or repeats across pages, `next_cursor` null at the end, malformed cursor 422;
  - version conflict on `PATCH` (409), and a successful edit bumping `version`;
  - archived idea gone from the list and `GET` (404);
  - RLS isolation: a second workspace's user gets 404 on the first workspace's idea and sees an empty list;
  - creator-or-owner rule: a plain member's `PATCH`/`DELETE` of another member's idea is 403, an owner's succeeds;
  - outbox: after `POST`, one `core.outbox` row of type `IdeaSubmitted` with the idea id; a failed create (validation) writes none;
  - the missing `X-Metis-Client` header on a mutation → 403.
- **Seam 2 — service**, only for `transition`, which has no route: every legal move succeeds and bumps `version`; every pair not in the table raises `IllegalTransition` (parametrized over all 9×9 pairs from the table itself plus a hand-written list of must-be-illegal moves, so the table cannot silently widen).
- **Migration**: a SQL replay test (prior art: `tests/modules/auth/test_auth_schema_migration.py`) checks the table has RLS and CHECK constraints, `metis_app` has privileges and default privileges on `ideas`, and the downgrade SQL revokes them.
- **Route-table auth**: add the ideas routes to the existing `test_route_auth.py` walk (no public allowlist entry).
- **Import check**: `uv run lint-imports` in CI with the new contracts.
- New tests live in `server/tests/modules/ideas/`, mirroring the package; shared fixtures come from `tests/modules/conftest.py`.
- Everything runs in `uv run pytest`; coverage for the new module ≥ 80%.

## Out of scope

- Starting runs, `run_graph`, runs API, SSE events (SHIP-225).
- Interview turns, specs, workflow runs (later issues; the module will own them).
- A stage-changing HTTP route, search, filters, sorting options, "restore from archive", hard delete.
- Score computation and writing `current_score` (SHIP-227).
- Notifications or handlers for `IdeaSubmitted` (the event is only written).
- Web UI.

## Touches

- `server/metis/modules/ideas/` (new: `__init__.py`, `controller/`, `service/`, `repo/`, `models/`, `dto/`, `helpers/`)
- `server/metis/core/errors.py` (`IllegalTransition`, `IdeaNotFoundError` if missing)
- `server/metis/entrypoints/api.py`
- `server/migrations/versions/0010_ideas.py`
- `server/tests/modules/ideas/` (new), `server/tests/modules/auth/test_route_auth.py`
- `server/pyproject.toml` (import-linter contracts)
- `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`, `AGENTS.md` (if the tree changes), Notion Metis LLD

## Dependencies

- `feat-jwt-auth` (SHIP-216): **done**, later replaced by server sessions; routes use `current_workspace`.
- `feat-outbox-relay` (`chore-outbox-relay`, SHIP-213): **done**; `core.outbox.add_event` and `DomainEventType.IDEA_SUBMITTED` exist.
- `refactor-auth-module` (SHIP-268): **done**; provides `auth` and `identity` as public modules.

## Acceptance criteria

- [x] A signed-in user can create, list, read, edit and archive ideas in their workspace (HTTP tests).
- [x] Title 3–120 and raw text 10–10,000 characters are enforced after trimming; invalid input is 422.
- [x] `GET /v1/ideas` returns `{items, next_cursor}`, newest first, with no gaps or repeats across pages.
- [x] `PATCH` with a stale `version` is 409; a successful edit bumps `version`.
- [x] `DELETE` archives; the idea is then absent from the list and 404 on read.
- [x] A user in another workspace cannot read, list or change the idea (RLS and queries both scoped).
- [x] Only the creator or a workspace owner can edit or archive; other members get 403.
- [x] `transition` accepts exactly the moves in the table; any other move raises `IllegalTransition` (409, `idea.invalid_transition`).
- [x] After `POST /v1/ideas` commits, one `IdeaSubmitted` row exists in `core.outbox` for that idea; none exists after a failed create.
- [x] Migration `0010` creates `ideas.ideas` with RLS and gives `metis_app` access to the `ideas` schema; its downgrade removes the table and the grants (replay-tested).
- [x] The ideas routes are covered by `test_route_auth.py`; `uv run lint-imports` passes with the new contracts.
- [x] `uv run ruff check`, `uv run mypy` and `uv run pytest` pass.
- [x] `server-context.md`, `architecture.md` and the Notion LLD describe the ideas module, schema and transition table.

## Open questions

None.

Resolved (2026-11-16):
- Transition table: the proposed table (Requirement 4 and the list below).
  - `intake → interviewing`; `interviewing → researching`; `researching → scoring`
  - `scoring → advising` (score < 55) or `spec_draft` (score ≥ 55)
  - `advising → interviewing`, `researching`, `scoring`
  - `spec_draft → spec_confirmed`; `spec_confirmed → spec_draft`, `planning`
  - `planning → exported`; `exported → planning`
- Edit and archive: creator or workspace owner; every member reads.
- Archive: nullable `archived_at` column; no `archived` stage.
- Test seams: HTTP main seam, service seam for `transition` only, migration SQL replay.

## Status

done
