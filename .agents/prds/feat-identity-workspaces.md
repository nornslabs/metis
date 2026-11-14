# PRD: feat-identity-workspaces

Linear: SHIP-214 · https://linear.app/heimdallabs/issue/SHIP-214/08-users-workspaces-and-members

## Problem / Goal

Metis is multi-user, and every tenant table hangs off `workspace_id`. But the `identity` schema is empty: there are no users, no workspaces and no membership, so nothing can own an idea and no tenant row can point at a real workspace. The next issue (SHIP-216, JWT auth and `/me`) needs a service it can call on every sign-in to turn token claims into a user and a workspace.

Goal: the `identity` module's tables and a pure-DB `service.py` for users, workspaces and membership. On first sign-in a user gets exactly one personal workspace; later sign-ins create nothing new. A user can create more workspaces and an owner can add existing users as members. RLS on `identity.members` keeps one workspace's membership invisible to another.

## User stories

1. As a new user, I want a user record created from my sign-in claims, so that Metis knows who I am.
2. As a returning user, I want my sign-in to update my name and image, so that my profile stays current without duplicate records.
3. As a returning user, I want a second sign-in to create no new user and no new workspace, so that my data stays in one place.
4. As a new user, I want a personal workspace created on my first sign-in, so that I can start submitting ideas right away.
5. As a new user, I want to be the owner of my personal workspace, so that I can manage it.
6. As a user, I want two sign-ins that race (two tabs) to still produce one user and one personal workspace, so that a double-click cannot split my data.
7. As a user, I want to list every workspace I am a member of, with my role in each, so that I can switch between them.
8. As a user, I want the list to never include workspaces I am not a member of, so that other teams' workspaces stay private.
9. As a user, I want to create a named workspace and become its owner, so that I can work with a team separately from my personal space.
10. As a workspace owner, I want to add an existing user by email as `owner` or `member`, so that we can collaborate.
11. As a workspace member who is not an owner, I want adding a member to be refused with a `Forbidden` error, so that only owners control access.
12. As a workspace owner, I want adding an email that matches no user to fail with a clear not-found error, so that I know they must sign in first (invites are later).
13. As a workspace owner, I want adding someone who is already a member to fail with a conflict, so that roles are not silently changed.
14. As a user, I want emails matched case-insensitively, so that `Ada@x.com` and `ada@x.com` are one person.
15. As a user, I want blank or invalid names and emails rejected, so that bad claims do not create broken records.
16. As a developer of SHIP-216, I want services that take my session and leave commit to me, so that sign-in (upsert user + ensure workspace) is one transaction.
17. As a developer, I want the services to set the RLS context themselves, so that callers cannot forget it and read nothing (or the wrong rows).
18. As a developer, I want a session with no workspace or user context to see zero member rows, so that a missing context fails closed.
19. As a developer, I want module code to reach identity only through `service.py`, so that module boundaries hold.
20. As an operator, I want `alembic upgrade head` and `downgrade -1` to work for the new migration, so that schema changes are reversible.
21. As a maintainer, I want tests that prove the three rules in the issue (first sign-in, second sign-in, cross-workspace list), so that regressions fail CI.

## Requirements

1. **Migration `0003_identity`** in schema `identity`:
   - `users(id uuid pk, auth_sub text not null unique, email text not null unique, name text null, image text null, created_at timestamptz not null default now())`. Email stored lower-cased and trimmed. Users are upserted on `auth_sub` (Decision 1).
   - `workspaces(id uuid pk, name text not null, is_personal boolean not null default false, created_by uuid not null references identity.users(id), created_at timestamptz not null default now())` with a partial unique index on `(created_by) WHERE is_personal` (Decision 2).
   - `members(workspace_id uuid not null references identity.workspaces(id) on delete cascade, user_id uuid not null references identity.users(id) on delete cascade, role text not null check (role in ('owner','member')), created_at timestamptz not null default now(), primary key (workspace_id, user_id))`, plus an index on `user_id`.
   - `SELECT enable_tenant_rls('identity.members'::regclass)`, plus a second permissive policy `member_self ON identity.members FOR SELECT USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid)` (Decision 3). With neither setting, zero rows are visible.
   - No RLS on `users` or `workspaces` (the issue scopes RLS to `members`; `workspaces` has no `workspace_id` column).
   - Downgrade drops the three tables (and any policy) in reverse order.
2. **Models** in `modules/identity/models.py` on `core.models.Base`, schema `identity`, native `uuid` columns (as `core.outbox` does), ids from `core.ids.uuid7`, UTC timestamps.
3. **Enum**: `MemberRole(StrEnum)` with `owner`, `member` in `schemas.py`; add it to the Domain Primitives table in `server-context.md`.
4. **Repo** (`repo.py`): SQLAlchemy queries only (get user by sub/email, insert-or-update user, insert workspace, insert member, get membership, list memberships with workspace join). No business rules.
5. **Schemas** (`schemas.py`): `UserClaims` (validated input: non-empty `sub`, valid email, optional name ≤ 200 chars, optional image URL), and read DTOs `User`, `Workspace`, `Membership` (workspace + role). Services return DTOs, not ORM rows.
6. **Service** (`service.py`, the module's public API). Every function takes an `AsyncSession` first, flushes but never commits; the caller owns the transaction (same rule as `core.outbox.add_event`). Each function sets the RLS context it needs with `set_config(..., true)` (transaction-local).
   - `upsert_user_from_claims(session, sub, email, name, image) -> User`: `INSERT … ON CONFLICT (auth_sub) DO UPDATE` so concurrent first sign-ins yield one row; updates `email`, `name`, `image` on later calls.
   - `ensure_personal_workspace(session, user) -> Workspace`: idempotent and race-safe; on first call creates the workspace named `Personal` with `is_personal = true` and an `owner` membership (`INSERT … ON CONFLICT DO NOTHING` on the partial unique index, then read back); afterwards returns the existing one.
   - `list_workspaces(session, user) -> list[Membership]`: sets `app.user_id`; every workspace the user is a member of, with role, ordered by `created_at`.
   - `create_workspace(session, user, name) -> Workspace`: validated non-empty name (≤ 100 chars, trimmed); creator becomes `owner`.
   - `add_member(session, actor, workspace_id, email, role) -> Membership`: actor must be an `owner` of the workspace, else `PermissionDeniedError` (`auth.forbidden`, 403). Actor not a member at all → also `PermissionDeniedError` (do not reveal the workspace exists). Unknown email → `NotFoundError` subclass with `workspace.member_not_found`. Already a member → `ConflictError` subclass with `common.conflict`.
7. **No events**: no `add_event` calls, no `events.py`, no `api.py` (routes are SHIP-216).
8. **Module exports**: `modules/identity/__init__.py` exports only the service functions, `MemberRole` and the DTOs.
9. **Docs sync**: `server-context.md` (`MemberRole` enum; identity service contract: session-in, caller commits, services set RLS context); `architecture.md` (the `members` policies: `tenant_isolation` plus `member_self` on `app.user_id`).

## Out of scope

- JWT verification, `current_user` / `current_workspace` dependencies, `/v1/me` and any route (SHIP-216).
- Switching the running services from `postgres` to a non-superuser app role (SHIP-216); tests use a test role.
- Invites by email, removing members, changing roles, leaving or deleting workspaces, transferring ownership.
- Provider keys and settings (other identity PRDs).
- Domain events from identity.
- Web UI.

## Touches

`server/metis/modules/identity/` (new: `__init__.py`, `models.py`, `repo.py`, `schemas.py`, `service.py`), `server/metis/core/errors.py` (identity error subclasses only, no new codes unless an open question needs one), `server/migrations/versions/0003_identity.py` (new), `server/tests/modules/identity/` (new), `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`, `README.md` (test role note).

## Dependencies

- `chore-migrations-rls` (SHIP-207): done. Provides the `identity` schema and `enable_tenant_rls`.
- `fix-foundation-gaps` (SHIP-262): done. Fixed `enable_tenant_rls` and the non-superuser RLS test pattern.
- `chore-outbox-relay` (SHIP-213): done. `0002_core_outbox` is the current migration head; `core.ids.uuid7` exists.
- Blocks: SHIP-216 (JWT auth, workspace scoping and `/me`).

## Test seam

One seam, the highest available: the public functions of `modules/identity/service.py`, called with a real `AsyncSession` on a Postgres migrated to head, where the session runs as a `NOLOGIN NOSUPERUSER NOBYPASSRLS` test role (`SET LOCAL ROLE`, granted on the `identity` schema). This is what SHIP-216 will call, and a non-superuser role is the only way RLS is actually exercised. Tests assert only returned DTOs, raised errors and row counts read back through the service. Repo and models are not tested directly.

Fixture pattern follows `tests/core/test_rls.py` and `tests/core/test_outbox.py`: `TEST_DATABASE_URL` (default `postgresql+asyncpg://postgres:postgres@localhost:5432/metis`), skip only when Postgres is unreachable or not migrated, truncate `identity` tables per test as the superuser.

Planned tests:

- First sign-in (`upsert_user_from_claims` + `ensure_personal_workspace`) → one user, one workspace, one `owner` membership.
- Second sign-in with the same `sub` and a new name → still one user (name updated), still one workspace.
- Two concurrent first sign-ins for the same `sub` → one user, one personal workspace.
- Emails differing only in case resolve to one user.
- User in A only → `list_workspaces` returns A, never B; user in A and B → returns both with correct roles.
- Session with no context reading `identity.members` as the test role → zero rows (fail closed).
- Owner adds an existing user → membership returned and visible in that user's `list_workspaces`.
- Non-owner member adds → `PermissionDeniedError`; non-member adds → `PermissionDeniedError`.
- Unknown email → not-found error; existing member → conflict error.
- `create_workspace` with blank name → validation error; valid name → creator is owner.
- Rolled-back transaction after `ensure_personal_workspace` → nothing persisted (caller owns commit).

## Acceptance criteria

- [x] All five services work and are covered by tests at the service seam.
- [x] First sign-in creates one user and one workspace; second sign-in creates nothing new.
- [x] RLS blocks cross-workspace reads of `identity.members`: a member of A cannot list B.
- [x] Only owners can add members (`PermissionDeniedError`, 403 `auth.forbidden`, otherwise).
- [x] `alembic upgrade head` and `downgrade -1` work for `0003_identity`.
- [x] `server-context.md` and `architecture.md` describe the identity contract and the `members` policy.
- [x] `uv run ruff check`, `uv run mypy`, `uv run pytest` pass.

## Open questions

None. Resolved 2026-11-14 (see Decisions):

1. The Auth.js `sub` is stored in `users.auth_sub text not null unique`; users are upserted on it, and email is updated each sign-in.
2. The personal workspace is marked with `workspaces.is_personal`, with a partial unique index on `(created_by) WHERE is_personal`, so Postgres enforces one per user even under races.
3. `identity.members` gets a second SELECT policy `member_self` (`user_id = app.user_id`) next to `tenant_isolation`; services set `app.user_id` to list a user's memberships. Still fails closed with no context.
4. Test seam confirmed: `service.py` only, real migrated Postgres, non-superuser test role; no repo-level tests.

## Review follow-ups (2026-11-14)

Applied after the two-axis code review:

- Services restore the caller's `app.workspace_id` / `app.user_id` after use, so SHIP-216's request scope is never silently switched.
- An email that belongs to another account raises `EmailTakenError` (409) via a savepoint, not a raw `IntegrityError`.
- `add_member` validates email and role (`NewMember`); `image` must be an http(s) URL; one shared `Email` type.
- `MemberUserNotFoundError` and new `WorkspaceNotFoundError` subclass `NotFoundError`; `PERSONAL_WORKSPACE_NAME` moved from repo to service.

Not changed: tests stay at the agreed service seam on real Postgres (no mocked-repo tests); blank optional `name`/`image` claims are treated as absent, not rejected.

## Status

done
