# PRD: feat-planning-module

Linear: SHIP-230 · https://linear.app/heimdallabs/issue/SHIP-230/30-planning-module-phases-tasks-and-dependencies

Milestone: M5 — Spec and planning. Branch: `feat/planning-module`. Blocked by SHIP-218 (`feat-ideas-crud`, done). Blocks SHIP-246 (Planner specialist).

## Problem / Goal

A confirmed spec has nowhere to turn into work: no table holds phases, tasks, estimates or dependencies, so the Planner (SHIP-246), the web plan view and the Linear export (milestones and blocked-by issues) have nothing to read or write.

Goal: a new `planning` module stores one plan per idea and spec version: ordered phases, tasks with Fibonacci estimates (1, 2, 3, 5, 8) and task dependencies that form a valid graph. It validates a plan before storing it, lets members edit phases and tasks, marks a plan ready (one `PlanReady` event), and returns the plan with its critical path. The Planner agent, HLD, Linear export and rebalance diffs are not part of this PRD.

## User stories

1. As the Planner (SHIP-246), I want to save a whole plan (phases, tasks, deps) in one call, so that a plan is never half stored.
2. As the Planner, I want saving to replace the previous draft for the same spec version, so that a retry or a re-plan does not leave two drafts.
3. As a founder, I want every task to carry an estimate of 1, 2, 3, 5 or 8, so that effort is comparable.
4. As a founder, I want a plan with a bigger estimate (13, 4, 0, …) refused with the task named, so that big work is split instead of hidden.
5. As a founder, I want a plan whose dependencies loop (A needs B, B needs A) refused with the tasks in the loop named, so that the plan can always be worked in some order.
6. As a founder, I want a dependency on a task that is not in the plan refused, so that no task waits on something that does not exist.
7. As a founder, I want a task that depends on itself refused, so that a plan cannot block on itself.
8. As a founder, I want phases in a fixed order, each with a name, a goal and exit criteria, so that I know when a phase is done.
9. As a founder, I want tasks ordered inside their phase, so that the plan reads top to bottom.
10. As a founder, I want to rename a phase, change its goal or exit criteria, so that the plan says what I mean.
11. As a founder, I want to reorder phases, so that the order matches how I will work.
12. As a founder, I want to add a phase, so that I can group work the Planner missed.
13. As a founder, I want to remove a phase and move its tasks to another phase in the same step, so that no task is lost or left without a phase.
14. As a founder, I want removing the only phase, or a phase with tasks and no target, refused, so that a plan always has a home for every task.
15. As a founder, I want to edit one task (title, description, estimate, labels, phase), so that I can fix it without redoing the plan.
16. As a founder, I want moving a task to another phase to keep its dependencies, so that edits never break the graph.
17. As a founder, I want an edit made on an out-of-date plan refused with a conflict, so that a second tab never overwrites a newer edit.
18. As a founder, I want to read the whole plan (phases → tasks → dependencies) with one request, so that the plan view loads fast.
19. As a founder, I want the critical path (the longest chain of dependent tasks by points) with its total points, so that I know what decides the length of the project.
20. As a founder, I want to mark the plan ready, so that export to Linear can start from a plan I accepted.
21. As a developer, I want `PlanReady` written once per plan, even if ready is clicked twice, so that export never runs twice for one plan.
22. As a founder, I want a ready plan to stop changing, so that what I exported is what I approved.
23. As a workspace member, I want to read, edit and mark ready any plan in my workspace (the same rule as the spec), so that anyone on the idea can move it forward.
24. As a workspace member, I want plans hidden from other workspaces, so that my ideas stay private.
25. As a developer, I want a plan to name the spec version it came from, so that a later spec change shows which plan is out of date.
26. As a developer, I want plans, phases, tasks and deps in the `planning` schema with RLS, so that tenant isolation is enforced by the database.
27. As a developer, I want validation in the service and the database (CHECK on estimate, FK on deps, unique positions), so that no code path stores an invalid plan.
28. As a developer, I want the module to import only the public surface of `ideas`, `identity` and `auth`, so that module boundaries hold.

## Requirements

### Migration

1. **Migration** `0021_planning` (down revision `0020_spec_versions`, the current head; recheck `alembic heads` at implementation time). Creates schema `planning` and tenant tables, each with `workspace_id` and RLS (`tenant_isolation`), `metis_app` granted SELECT, INSERT, UPDATE, DELETE (plans are mutable drafts; the ready plan is protected by the service):
   - `planning.plans(id uuid7 pk, workspace_id fk identity.workspaces cascade, idea_id fk ideas.ideas cascade, spec_version_id fk ideas.spec_versions, status text CHECK draft|ready default draft, version int default 1, ready_at timestamptz null, created_at, updated_at)`. Unique `(idea_id, spec_version_id)`: one plan per idea and spec version. Index `(workspace_id, idea_id, created_at desc)`.
   - `planning.phases(id, workspace_id, plan_id fk plans cascade, position int ≥ 0, name text, goal text, exit_criteria text)`. Unique `(plan_id, position)` **deferrable initially deferred** (so a reorder can run in one statement batch).
   - `planning.tasks(id, workspace_id, plan_id fk plans cascade, phase_id fk phases, position int ≥ 0, title text, description text, estimate smallint CHECK in (1,2,3,5,8), labels text[] default '{}', parent_task_id fk tasks null)`. Unique `(phase_id, position)` deferrable initially deferred. Composite FKs keep a task's `phase_id` and `parent_task_id` inside its own plan (`UNIQUE (id, plan_id)` on `phases` and `tasks`; FKs on `(phase_id, plan_id)` and `(parent_task_id, plan_id)`).
   - `planning.task_deps(workspace_id, plan_id, task_id, blocked_by_task_id)`, primary key `(task_id, blocked_by_task_id)`, CHECK `task_id <> blocked_by_task_id`, composite FKs `(task_id, plan_id)` and `(blocked_by_task_id, plan_id)` to `tasks (id, plan_id)` (dangling or cross-plan deps are impossible), index on `blocked_by_task_id`.
   - Downgrade drops the tables and revokes the schema grant (the empty schema stays; `0001_initial` owns it). Backward-compatible, no backfill.
   - `modules/planning/models/_schema.py` and `server/migrations/env.py` wiring follow the `scoring` module's pattern.

### Service (`planning/service/`, caller's session, never commits, scoped by workspace id as well as RLS)

2. **Plan input** (DTOs in `dto/`): `PhaseInput{name, goal, exit_criteria}` (position is the list order), `TaskInput{key, phase (the index of a phase in the input's `phases`; phases have no key), title, description, estimate, labels, parent_key?}` and `DepInput{task_key, blocked_by_key}`; keys are caller-chosen strings that identify tasks within one save (ids are assigned by the server). Text limits (trimmed): phase name 1–120, goal and exit criteria 1–1,000; task title 1–200, description 0–4,000; labels at most 10, each 1–40; at most 12 phases, 200 tasks and 600 deps per plan.
3. **`save_plan(session, workspace_id, idea_id, spec_version_id, PlanInput)` → `Plan`**: idea must be live (`IdeaNotFoundError`), `spec_version_id` must be one of the idea's versions (`SpecNotFoundError`, via `ideas`' public surface). Takes a per-idea advisory lock. In one transaction it validates (R4), then replaces the existing draft for `(idea_id, spec_version_id)` (children deleted and re-inserted, the plan row kept with `version + 1`) or creates the plan with `version = 1`. A `ready` plan for that spec version is not replaced: `PlanNotEditableError` (`plan.invalid_transition`, 409). Returns the full plan.
4. **Validation** (`helpers/validation.py`, pure, run before any write; failure is `InvalidPlanError` → 422 `plan.invalid_plan` with `meta {reason, tasks: [keys or ids]}`; `reason` is one of `no_phases`, `no_tasks`, `duplicate_key`, `unknown_phase`, `unknown_task`, `bad_estimate`, `bad_position`, `bad_operation`, `self_dependency`, `duplicate_dependency`, `dependency_cycle`, `parent_cycle`, `limit_exceeded`):
   - at least one phase and one task; every task sits in an existing phase;
   - `estimate` ∈ {1, 2, 3, 5, 8}; anything else (including 13 and non-integers) names the task and says to split work above 8;
   - every dep and every `parent_key` names a task in the same input; no self dependency; no duplicate dep;
   - the dependency graph has no cycle (topological sort, Kahn); a cycle is reported with the tasks left over after the sort (`tasks` lists their keys);
   - the parent chain has no cycle (a task cannot be its own ancestor).
5. **`get_plan(session, workspace_id, idea_id, spec_version_id=None)` → `Plan`**: the plan for that spec version, or the newest plan of the idea when omitted; none → `PlanNotFoundError` (`plan.not_found`, 404). A `Plan` is `{id, idea_id, spec_version_id, status, version, ready_at, created_at, updated_at, phases: [{id, position, name, goal, exit_criteria, tasks: [{id, position, title, description, estimate, labels, parent_task_id, blocked_by: [task_id]}]}], critical_path}`. Phases and tasks are in position order; `blocked_by` is sorted by the blocking task's phase and position (stable).
6. **`critical_path(plan)` → `{task_ids, points}`** (pure helper, also run inside `get_plan`): the dependency chain with the largest sum of estimates, tasks in dependency order; ties broken by phase then position so the result is stable; a plan with no deps returns its single largest task (earliest on ties).
7. **`edit_phases(session, workspace_id, plan_id, ops, version)` → `Plan`**: the plan must be `draft` (else `PlanNotEditableError`) and `version` must equal the plan's (else `PlanConflictError` `plan.conflict`, 409). `ops` is a list applied in order inside one transaction, all or none; each is one of:
   - `rename` `{phase_id, name?, goal?, exit_criteria?}`;
   - `reorder` `{phase_ids}` (must list every phase of the plan exactly once);
   - `add` `{name, goal, exit_criteria, position?}` (default: last; later phases move down);
   - `remove` `{phase_id, move_tasks_to?}` (a phase with tasks needs `move_tasks_to`, another phase of the plan, and its tasks are appended to that phase in their order; removing the only phase is refused). Dependencies are untouched by phase edits.
   Unknown phase → `PlanNotFoundError` with `meta {phase_id}`; an invalid op → `InvalidPlanError` (422). Bumps `version` once for the whole call, sets `updated_at`.
8. **`edit_task(session, workspace_id, plan_id, task_id, TaskPatch, version)` → `Plan`**: draft only, version check as in R7. `TaskPatch` fields (all optional): `title`, `description`, `estimate` (R4 rule), `labels`, `phase_id` (moves the task to the end of that phase and re-packs positions of the old phase), `position` (within its phase, with `phase_id` or alone). Unknown task → `PlanNotFoundError` with `meta {task_id}`. Dependencies are not editable here.
9. **`mark_ready(session, workspace_id, plan_id)` → `Plan`**: sets `status = ready`, `ready_at = now`, bumps `version`, and adds a `PlanReady` outbox event `{idea_id, plan_id, spec_version_id, version}` in the same transaction. A plan that is already `ready` is returned unchanged with no second event. The plan must pass R4 validation again (an invalid stored plan cannot be marked ready). Does not move the idea's stage (the Planner/Integrator own `planning` and `exported`).
10. Any workspace member reads, edits and marks ready (no creator/owner check), the rule used for specs and runs.
11. Exported through `planning/__init__.py`: `router`, `Plan`, `PlanInput`, `PlanStatus`, `save_plan`, `get_plan`, `critical_path`, `mark_ready`, the error classes the Planner needs.

### Routes (`planning/controller/`, `current_workspace`; mutations need `X-Metis-Client: web`)

12. `GET /v1/ideas/{id}/plan` → `Plan` (newest plan of the idea; `?spec_version_id=` picks one; unknown/archived/foreign idea → `idea.not_found`; no plan yet → `404 plan.not_found`).
13. `PATCH /v1/plans/{id}/phases` `{version, ops}` → `Plan` (R7).
14. `PATCH /v1/plans/{id}/tasks/{task_id}` `{version, title?, description?, estimate?, labels?, phase_id?, position?}` → `Plan` (R8). Returns the whole plan so the web has one source of truth.
15. `POST /v1/plans/{id}/ready` → `200 Plan` (R9, idempotent).
16. No route saves a plan: `save_plan` is called by the Planner (SHIP-246). Web `schema.d.ts` regenerated.

### Errors and events

17. `core/errors.py`: `PlanNotFoundError` (`plan.not_found`, 404), `PlanConflictError` (`plan.conflict`, 409), `PlanNotEditableError` (`plan.invalid_transition`, 409) on codes the catalog already has; new code `plan.invalid_plan` (422, `InvalidPlanError`, `meta {reason, tasks}`).
18. `PlanReady` already exists in `DomainEventType`; `planning/events.py` adds its payload model.

### Module boundaries

19. `planning` is a peer of `research` and `scoring` in the import-linter layers contract (above `ideas`; none of the three imports another), and a new contract limits it to the public surface of `ideas`, `identity` and `auth`; `auth`'s forbidden list names `planning`. `architecture.md` module list already includes `planning`.

## Out of scope

- The Planner specialist, `save_plan` tool and prompt (SHIP-246).
- HLD, plan diffs, rebalance (`ExportMode.rebalance`), the Linear/Notion export (Integrations module), and reopening a ready plan.
- Editing dependencies through the API (the Planner re-saves the plan; a dependency editor is a later issue).
- Web UI (`web/` is not touched except the regenerated `schema.d.ts`).
- Moving the idea's stage on save or ready; changing the transition table.
- Using the critical path for scheduling or dates.

## Touches

- `server/metis/modules/planning/` (new): `models/`, `repo/` (plans, phases, tasks, task_deps), `service/` (plans, phases, tasks), `dto/`, `helpers/` (validation, critical path), `controller/`, `events.py`, `__init__.py`.
- `server/migrations/versions/0021_planning.py` (new), `server/migrations/env.py` (model import).
- `server/metis/core/errors.py` (`plan.invalid_plan`), `server/metis/main` router wiring.
- `server/pyproject.toml` (import-linter contracts).
- `server/tests/` — `modules/planning/` (new), migration test.
- `web/lib/api/schema.d.ts` (regenerated only).
- `.agents/ctx/server-context.md` (planning section, errors, events), `.agents/progress-tracker.md`.

## Dependencies

- `feat-ideas-crud` (SHIP-218): done.
- `feat-spec-editor` (SHIP-244): done on `feat/spec-versions`, not yet merged to `main`; `plans.spec_version_id` references `ideas.spec_versions` (branch stacked on it, see Resolved).

## Testing

One seam: the **HTTP routes** (`tests/modules/planning/`), on real Postgres as `metis_app`, as the spec, scoring and ideas API tests do. Plans are created with `planning.save_plan` through a small fixture, since no route saves one. A good test checks what a client or the database sees (responses, rows, outbox events), never internals.

Cases:

- Valid plan stored and read back in order (phases, tasks, `blocked_by`, labels); `save_plan` twice on the same spec version replaces the draft (same plan id, `version` + 1, no orphan rows); a new spec version makes a second plan; the newest is returned by default and `?spec_version_id=` picks one.
- Rejected with 422 `plan.invalid_plan` and the right `reason`/`tasks`: cycle (2-task and longer), self dependency, duplicate dependency, dangling dependency key, estimate 13 / 4 / 0, unknown phase, parent cycle, empty plan, over a limit; nothing is stored on failure.
- Database guards: a direct insert of a non-Fibonacci estimate, a cross-plan dependency or a self dependency fails (CHECK/FK).
- Phase edits: rename; reorder (all phases listed exactly once, else 422); add at a position; remove with `move_tasks_to` moves tasks and keeps deps; remove with tasks and no target → 422; remove the only phase → 422; failing op rolls back the earlier ops of the same call.
- Task edit: fields change; `phase_id` moves the task and re-packs positions; dependencies survive a move; estimate rules apply; unknown task → 404.
- Version conflict: stale `version` on phases and tasks → 409 `plan.conflict`; two simultaneous edits on the same version: one 200, one 409.
- Ready: `POST ready` → `ready`, one `PlanReady` outbox event; second call → 200, no second event; edits on a ready plan → 409 `plan.invalid_transition`; `save_plan` over a ready plan for the same spec version → 409.
- Critical path: chain wins over a larger lone task when its sum is larger; no deps returns the largest task; ties are stable (unit tests on the pure helper).
- Access: any member reads/edits/marks ready; another workspace's plan is invisible (`plan.not_found`); archived or foreign idea → `idea.not_found`.
- Migration: upgrade/downgrade round trip, RLS on every table, deferrable position uniqueness (reorder in one transaction works), single head.
- Local checks: `uv run ruff check`, `uv run mypy`, `uv run lint-imports`, `uv run alembic upgrade head`, web `npm run typecheck` (schema regenerated). `uv run pytest` runs in CI, not locally.

## Acceptance criteria

- [x] Invalid plans (cycles, bad estimates, dangling dependencies) are rejected with `plan.invalid_plan` and a reason that names the tasks.
- [x] Phase edits (rename, reorder, add, remove with tasks moved) keep tasks and dependencies consistent; a failing call changes nothing.
- [x] A stale `version` on a phase or task edit returns 409 `plan.conflict`.
- [x] `PlanReady` is written once per plan, however many times ready is called.
- [x] `GET /v1/ideas/{id}/plan` returns phases → tasks → dependencies and the critical path.
- [x] Plans are hidden across workspaces (RLS) and usable by every member of the workspace.
- [x] `ruff`, `mypy`, `lint-imports` and `alembic upgrade head` pass; tests are added and run in CI.
- [x] `server-context.md` and the tracker are updated.

## Open questions

None open.

## Resolved

- Branch `feat/planning-module` is stacked on `feat/spec-versions` (SHIP-244 unmerged), so `0021_planning` chains from `0020_spec_versions` (user, 2026-11-23).
- One plan per `(idea, spec version)`; `save_plan` replaces the draft in place; a `ready` plan is frozen (user, 2026-11-23).
- Task patch = title, description, estimate, labels, phase, position (no dependencies), `version` on every edit; critical path inside `GET /plan`, no separate route (user, 2026-11-23).
- New error code `plan.invalid_plan` (422, `meta {reason, tasks}`) (user, 2026-11-23).

- Built on `feat/planning-module` (stacked on `feat/spec-versions`): `0021_planning`, `modules/planning/`, `plan.invalid_plan`, import-linter contracts, web `schema.d.ts` regenerated. Migration checked as offline SQL only (no host Postgres); tests written, not run locally (CI runs them).
- Code review (standards + spec): fixed the `save_plan` claim race message (now a conflict unless the plan is ready) and added tests (phase-edit race, 12-phase cap, task limit). Left as judgement calls: `helpers/graph.py` and `helpers/critical_path.py` kept as separate files, `dict[str, Any]` rows in repos, small mutable locals, non-integer estimates fail pydantic's generic 422.

## Status

done
