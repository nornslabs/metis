# PRD: refactor-auth-module

Linear: SHIP-268 · https://linear.app/heimdallabs/issue/SHIP-268/12b-move-auth-users-and-sessions-into-the-auth-module-and-schema

Milestone: M1 — Identity and workspaces. Follows 12A (SHIP-264 → SHIP-265 → SHIP-267, all done). Branch: `refactor/auth-module`.

## Problem / Goal

After 12A, everything about "who are you" lives in `modules/identity`, next to workspaces, members, provider keys and settings. That covers users, sessions, sign-in identities, the OAuth flow, the Google provider, and the auth routes and dependencies. Its tables `identity.users`, `identity.sessions` and `identity.auth_identities` sit in the `identity` schema. This causes three problems:

- It breaks the rule "one module, one schema, public API through `service.py`" (`architecture.md`).
- `identity` is the largest module (~2,000 lines), so a change to sign-in touches the same files as a change to workspaces.
- `auth_service` reaches into `identity.repo` and `UserRow`. `auth_deps.current_workspace` reaches back into `identity.service`. That is internal coupling in both directions, and email sign-in would make it worse.

Goal: a new `modules/auth` owns **who you are**: users, sessions, sign-in identities, OAuth and providers. Its tables live in an `auth` Postgres schema. `identity` owns **where you work**: workspaces, members, provider keys, settings and `current_workspace`. Imports go one way: `identity → auth`, and `auth` imports no other module.

**No behavior change except one.** Routes, status codes, error codes, cookies, Redis keys, log events and RLS stay the same. The one change is *when* the personal workspace is created: on the first `/me` or workspace-scoped call, not at sign-in (Requirement 5).

## User stories

1. As a signed-in user, I want my existing session cookie to keep working after the deploy that moves the tables, so that a refactor doesn't sign me out.
2. As a signed-in user, I want every route to answer exactly as before (bodies, status codes, error codes), so that the web app needs no change.
3. As a visitor, I want `GET /v1/auth/providers`, `GET /v1/auth/google/login` and `GET /v1/auth/google/callback` to keep their paths and redirects, so that the Google OAuth redirect URI stays valid.
4. As a user, I want `POST /v1/auth/logout` and `POST /v1/auth/logout-all` to behave as before (idempotent logout, CSRF header, cookie cleared), so that signing out is unchanged.
5. As a user, I want sessions to stay revoked after the move (Redis tombstones and the cache keep their `auth:session:*` keys), so that a logout from before the deploy still holds after it.
6. As a user signing in with Google, I want my account found by `(provider, subject)` or linked by email exactly as before, so that the move doesn't create duplicate users.
7. As a new user, I want my personal workspace to exist on my first `/me` or workspace-scoped call, so that the app opens in my workspace as it does today.
8. As a new user, I want two concurrent first requests to create only one personal workspace, so that I never see a duplicate.
9. As a member, I want `X-Workspace-Id` and RLS scoping to behave exactly as before, so that I only ever see my own workspace's data.
10. As a workspace owner, I want inviting a member by email to work as before, including "no user with that email", so that membership is unchanged.
11. As an operator, I want `alembic upgrade head` to move `users`, `sessions` and `auth_identities` into a new `auth` schema without copying data, so that the migration is instant and safe.
12. As an operator, I want the foreign keys from `identity.workspaces.created_by` and `identity.members.user_id` to keep pointing at the moved `users` table, so that workspace ownership and membership survive the move.
13. As an operator, I want deleting a user to still cascade to their sessions, sign-in identities and memberships, so that cleanup works as before.
14. As an operator, I want `metis_app` to have the same rights on the `auth` schema as on `identity`, default privileges included, so that the api and workers don't fail with "permission denied" after the move.
15. As an operator, I want `alembic downgrade` to move all three tables back to `identity` and drop the `auth` schema, so that a rollback is possible.
16. As a developer, I want `modules/identity/` to contain no user-table, session, OAuth, provider or sign-in code, so that I know where sign-in code lives.
17. As a developer, I want `metis.modules.auth` to export only `router`, `current_user`, `CurrentUserDep`, `check_csrf`, `SessionUser`, `User`, `get_user` and `find_user_by_email`, so that other modules depend on a small, stable surface.
18. As a developer, I want `auth` to import no other module, so that auth can grow (email sign-in, new providers) without knowing about workspaces.
19. As a developer, I want identity to use only auth's public surface, so that auth stays the owner of the user tables.
20. As a developer, I want `current_workspace` / `CurrentWorkspaceDep` in identity, built on `auth.CurrentUserDep`, so that workspace logic stays with workspaces.
21. As a developer, I want `insert_or_none` in `core/db.py`, so that both modules' repos share it without a cross-module import.
22. As a developer, I want the import rules enforced by `lint-imports` in CI, so that a stray import fails the build instead of getting through review.
23. As a developer, I want `import metis.modules.auth` to work in a fresh Python process, so that auth has no hidden dependency on identity.
24. As a developer, I want the auth tests under `tests/modules/auth/`, mirroring `metis/modules/auth/`, so that tests stay next to the code they cover.
25. As a developer, I want the sign-in helpers and the DB/Redis/client fixtures shared by both test packages, so that the auth and identity tests don't copy setup.
26. As a developer, I want `git log --follow` to show history for the moved files, so that `git blame` survives the move.
27. As a developer, I want every existing test to pass with only imports and paths changed (except personal-workspace timing), so that I can trust the refactor changed nothing else.
28. As an agent reading the docs, I want the AGENTS.md tree, `architecture.md`, `server-context.md`, the Metis LLD and the auth plan to describe the `auth` module, its schema and the import rule, so that I build against the real layout.

## Requirements

1. **Create `modules/auth/` by moving code** out of `modules/identity/` (`git mv` for whole files, so history is kept):
   - `auth_api.py` → `auth/api.py`, `auth_service.py` → `auth/service.py`, `auth_deps.py` → `auth/deps.py` (without `current_workspace`; see 4).
   - `oauth_flow.py`, `sessions_repo.py`, `identities_repo.py` and `providers/` (`__init__.py`, `base.py`, `google.py`) move unchanged apart from imports.
   - `UserRow`, `AuthIdentityRow` and `SessionRow` → `auth/models.py` with `SCHEMA = "auth"`. The FKs from sessions and identities point at `auth.users.id` (`ondelete="CASCADE"`).
   - `get_user`, `get_user_by_email` and `insert_user` from `identity/repo.py` → new `auth/users_repo.py`.
   - `User`, `UserClaims` and the session and sign-in types (`SessionRecord`, `CacheLookup`, `SessionRejection`, `NewSession`, `ActiveSession`, `SessionUser`, `SignInOutcome`, `SignedIn`) → `auth/schemas.py`.
   - `CLIENT_HEADER`, `WEB_CLIENT` and `SAFE_METHODS` move with `auth/deps.py`. `WORKSPACE_HEADER` moves with `current_workspace`.
2. **Public surface of `auth`** (`auth/__init__.py`): `router`, `current_user`, `CurrentUserDep`, `check_csrf`, `SessionUser`, `User`, `get_user`, `find_user_by_email`, and nothing else.
   - `get_user(session, user_id) -> User | None` and `find_user_by_email(session, email) -> User | None` live in `auth/service.py`. They take the caller's session, never commit, and wrap `users_repo`. `find_user_by_email` normalizes the email the same way `add_member` does today, so lookups match.
   - `auth` imports nothing from `metis.modules` outside `metis.modules.auth`.
3. **Identity keeps** workspaces, members, provider keys and settings.
   - Its service, schemas (`MeResponse`, …) and routes use `auth.User` and `auth.CurrentUserDep`.
   - `add_member` finds the invited person through `auth.find_user_by_email`. It keeps `MemberUserNotFoundError` and `AlreadyMemberError`, and its RLS context.
   - Identity imports only `metis.modules.auth` (the public surface), never `auth.service`, `auth.models`, repos or `auth.schemas` directly.
   - `identity/__init__.py` drops `SessionUser`, `User`, `current_user`, `CurrentUserDep`, `check_csrf` and `auth_router`, and gains `current_workspace` and `CurrentWorkspaceDep`.
4. **New `identity/deps.py`** with `current_workspace` and `CurrentWorkspaceDep`, built on `auth.CurrentUserDep`. Same header, 422 on a bad UUID, 403 on a foreign or unknown workspace, `set_user` + `set_workspace` + `bind_context`.
5. **Lazy personal workspace** (the one behavior change):
   - `SessionUser` becomes `user` + `session_id`; it no longer carries `personal_workspace`. `SignedIn` drops `personal_workspace` too.
   - `sign_in` and `get_session_user` no longer call `ensure_personal_workspace`. `sign_in` keeps its order (`(provider, subject)`, then email, then create), savepoints, single retry and log events.
   - `current_workspace` calls `identity.service.ensure_personal_workspace` (already idempotent, same transaction) when no `X-Workspace-Id` is sent, and uses its id as the target.
   - `/me` gets its personal workspace through `CurrentWorkspaceDep`, which it already depends on. With no header, the personal workspace exists before `list_workspaces` runs. With a header, `/me` also calls `ensure_personal_workspace`, so a first `/me` always creates it.
   - Calls that are not workspace-scoped (`GET/POST /v1/workspaces`, `/v1/auth/*`) don't create it. A brand-new user who calls only `GET /v1/workspaces` first sees an empty list. This is accepted.
6. **`insert_or_none` moves** from `identity/repo.py` to `core/db.py`, and both modules' repos import it from there. It stays generic (no module imports).
7. **Migration `0008_auth_schema`** (don't edit `0003`, `0006` or `0007`):
   - Upgrade:
     - `CREATE SCHEMA auth`.
     - `ALTER TABLE identity.users SET SCHEMA auth`, and the same for `identity.sessions` and `identity.auth_identities`. Indexes, constraints and FKs move with the tables and keep their names. FKs from `identity.workspaces` and `identity.members` follow the table, because Postgres tracks FKs by table, not by name.
     - Grant `metis_app` on `auth` what `0004_app_role.py` grants on `identity`: `USAGE` on the schema; `SELECT, INSERT, UPDATE, DELETE` on all tables; `USAGE, SELECT` on all sequences; and the matching `ALTER DEFAULT PRIVILEGES`. The migration is self-contained, so it copies 0004's constants instead of importing them.
   - Downgrade:
     - Move all three tables back to `identity`.
     - Revoke the `auth` grants and default privileges.
     - `DROP SCHEMA auth` (not `CASCADE`, so it fails loudly if anything else landed there).
   - Keep the SQL as module-level constants (as in `0007`), so a test can replay it.
   - Alembic metadata: `migrations/env.py` uses `target_metadata=None`, so nothing needs registering. The model `SCHEMA` constants and FK targets are the only metadata change.
8. **Import rules with import-linter**: add `import-linter` as a dev dependency (via `uv add --dev`), put the contracts in `server/pyproject.toml`, and add a `uv run lint-imports` step to the server job in `.github/workflows/ci.yml`. Contracts:
   - `metis.core` and `metis.helpers` import nothing from `metis.modules`.
   - `metis.modules.auth` imports no other `metis.modules.*` package.
   - `metis.modules.identity` may import `metis.modules.auth`; nothing in auth may import identity. A layers contract (`identity` above `auth`) covers this.
9. **Wiring**: `entrypoints/api.py` includes `auth.router` (from `metis.modules.auth`) and `identity.router`. The route table and URL paths stay the same.
10. **Tests** (see Testing decisions):
    - `tests/modules/auth/` gets `test_auth_google_api.py`, `test_auth_sessions_api.py`, `test_route_auth.py`, `fake_google.py` and `session_probe.py`, moved with `git mv`. Only imports, paths and the personal-workspace timing change.
    - The shared sign-in helpers (`google_profile`, `create_user`, `sign_in`, `auth`, `assert_problem`) move to `tests/helpers/` as the issue says (a non-test module, e.g. `tests/helpers/auth.py`). The `engine` / `redis` / `client` / `http` fixtures move to `tests/modules/conftest.py`, so both packages inherit them.
    - The engine fixture's readiness check also requires `auth.users` and `auth.sessions`. `TRUNCATE` in test setup targets `auth.users` (it still cascades to sessions, identities and members).
    - `test_identity_service.py` creates users through `auth`'s sign-in helper or a fixture, not `identity` code, and grants its test role on the `auth` schema as well. `test_rls.py` is checked: today it creates no users, so it needs a change only if the move breaks it.
11. **Docs** (Keeping Docs in Sync):
    - The AGENTS.md folder tree: identity owns workspaces, members, keys and settings; the new `auth` owns users, sessions and sign-in.
    - `architecture.md`: the module list, the `auth` schema, the one-way `identity → auth` import rule and its enforcement by import-linter, the providers' path (`modules/auth/providers/`), and lazy personal-workspace creation.
    - `server-context.md`: the module table, the auth contract's new paths, the `auth.*` table names, `metis_app` grants on `core`, `identity` and `auth`, and the `lint-imports` check.
    - Notion Metis LLD: `identity.users` → `auth.users`, the schema list, and the identity and auth module sections.
    - The auth plan page.

## Implementation decisions

- **No behavior change is the contract**, apart from Requirement 5. Error codes (`auth.*`), log event names, Redis keys, cookie name and attributes, route paths, OpenAPI tags and the public-route allowlist in `test_route_auth.py` stay as they are.
- **No RLS on `auth.*`** (same as today). Users, sessions and identities aren't tenant data, and only `auth` reads them.
- **Errors stay in `core/errors.py`**, since the error catalog is shared. `MemberUserNotFoundError` stays an identity error.
- **`SET SCHEMA` keeps per-table grants.** The new grants and default privileges cover tables added to `auth` later.
- **`ensure_personal_workspace` runs before `set_user` / `set_workspace`** in `current_workspace`, in the request transaction. Today it runs at the same point inside `current_user`, so its RLS handling is unchanged.
- **Identity drops `User` from its own exports.** Callers import `User` from `metis.modules.auth`. One owner, one import path.
- **No circular import is possible**, because auth never imports identity. That's why `import metis.modules.auth` works in a fresh process.
- **Fixtures go in `tests/modules/conftest.py`**, because pytest fixtures must live in a `conftest.py` to be inherited. The helper *functions* go in `tests/helpers/` as the issue says.

## Testing decisions

Good tests here check only what a client or operator can see: HTTP responses, cookies, rows in the database, privileges in the catalog. They don't check which file a function lives in. Passing the existing tests unchanged is the main proof of "no behavior change".

- **Seam 1 — HTTP (main seam)**, as in SHIP-264/265/267. The moved auth tests and the identity API tests drive the app through `httpx` against real Postgres (as `metis_app`) and Redis.
  - `test_route_auth.py` moves to `tests/modules/auth/` and still walks every route, identity's included.
  - **New: lazy personal workspace.**
    - A freshly signed-in user has no personal workspace yet. Their first `/me` creates it and returns it as `current_workspace`.
    - A first workspace-scoped call without `X-Workspace-Id` (e.g. `GET /v1/settings`) also creates it.
    - Two concurrent first calls create exactly one.
  - `test_auth_google_api.py`'s first-sign-in test now asserts the personal workspace after the first `/me`, not straight after the callback. This is the only allowed assertion change.
  - `add_member` by email still works and still returns "no user with that email" (existing tests, unchanged).
- **Seam 2 — migration SQL replay**, following the prior art `test_downgrade_restores_auth_sub_from_google_identities`. The test runs in a rolled-back transaction:
  1. Sign in and create a session at head.
  2. Replay `0008`'s downgrade SQL and check the three tables are in `identity`.
  3. Replay the upgrade SQL and check they are in `auth`.
  4. Resolve the same cookie through the session service with the Redis cache cleared, so the lookup really hits the moved table.
  - Also checked:
    - The FKs `fk_workspaces_created_by_users` and `fk_members_user_id_users` reference `auth.users` (`pg_constraint`).
    - Deleting a user cascades to members, sessions and identities.
    - `metis_app` has the table privileges on `auth.*` (`has_table_privilege`) and default privileges on `auth` (`pg_default_acl`).
- **Seam 3 — service**: `auth.get_user` / `find_user_by_email` (found, missing, email case and whitespace) in a new `tests/modules/auth/test_auth_service.py`. `test_identity_service.py` covers `add_member` through `auth.find_user_by_email`, running as the `metis_identity_test` role as today.
- **Import check**: `lint-imports` runs in CI. One pytest runs `python -c "import metis.modules.auth"` in a subprocess and expects exit code 0.
- Everything runs in `uv run pytest`. CI additionally runs `uv run lint-imports`.

## Out of scope

- Any other behavior change: new routes, new error codes, changed cookie or session semantics.
- Rate limiting, session rotation, email sign-in, new providers.
- Splitting other modules, or moving provider keys and settings out of identity.
- Editing migrations `0003`, `0006` or `0007`.
- Web changes (the web app already calls `/me` first).

## Touches

- `server/metis/modules/auth/` (new: `__init__.py`, `api.py`, `service.py`, `deps.py`, `oauth_flow.py`, `sessions_repo.py`, `identities_repo.py`, `users_repo.py`, `models.py`, `schemas.py`, `providers/`)
- `server/metis/modules/identity/` (`__init__.py`, `api.py`, new `deps.py`, `service.py`, `repo.py`, `models.py`, `schemas.py`)
- `server/metis/core/db.py` (`insert_or_none`)
- `server/metis/entrypoints/api.py`
- `server/migrations/versions/0008_auth_schema.py`
- `server/tests/modules/auth/` (new), `server/tests/modules/identity/`, `server/tests/modules/conftest.py` (new), `server/tests/helpers/` (shared sign-in helper), `server/tests/core/test_rls.py` (only if needed)
- `server/pyproject.toml`, `server/uv.lock` (via `uv add --dev import-linter`), `.github/workflows/ci.yml`
- `AGENTS.md`, `.agents/ctx/architecture.md`, `.agents/ctx/server-context.md`, Notion Metis LLD and auth plan

## Dependencies

- `refactor-remove-jwt-auth` (SHIP-267): **done** (PR #27 merged into `feat/server-owned-auth`).
- Note: `main` doesn't have 12A yet; PR #28 (`feat/server-owned-auth` → `main`) is still open. See open question 1.

## Acceptance criteria

- [ ] `modules/auth` imports nothing under `metis.modules` except itself. `uv run lint-imports` passes locally and in CI.
- [ ] `modules/identity/` contains no user-table, session, OAuth, provider or sign-in code (no `UserRow`, `auth_*`, `oauth_flow`, `sessions_repo`, `identities_repo`, `providers/`, `get_user*`, `insert_user`).
- [ ] `metis.modules.auth` exports exactly `router`, `current_user`, `CurrentUserDep`, `check_csrf`, `SessionUser`, `User`, `get_user`, `find_user_by_email`.
- [ ] `current_workspace` / `CurrentWorkspaceDep` live in `identity/deps.py`. `insert_or_none` lives in `core/db.py`.
- [ ] After `alembic upgrade head`, `users`, `sessions` and `auth_identities` are in the `auth` schema. The FKs from `identity.workspaces` and `identity.members` reference `auth.users` (tested). `metis_app` has the same privileges and default privileges there as on `identity`.
- [ ] A session created before the migration still resolves the same cookie after it. The `0008` downgrade moves all three tables back to `identity` and drops the `auth` schema (tested by SQL replay).
- [ ] A new user's personal workspace exists after their first `/me` or workspace-scoped call, and concurrent first calls create one (tested).
- [ ] `import metis.modules.auth` works in a fresh Python process (tested).
- [ ] Moved files keep history (`git log --follow server/metis/modules/auth/service.py` shows the `auth_service.py` commits).
- [ ] Every existing test passes with only imports and paths changed, apart from the personal-workspace timing. The route-table test still covers every route.
- [ ] `uv run ruff check`, `uv run mypy` and `uv run pytest` pass.
- [ ] The AGENTS.md tree, `architecture.md`, `server-context.md`, the Notion LLD and the auth plan describe the `auth` module, schema and import rule.

## Open questions

None.

Resolved (2026-11-15):
- Checked against the full SHIP-268 description (Linear `get_issue`, 2026-11-15): Requirements and acceptance criteria match. One difference: the issue says `test_rls.py` creates users directly, but it only uses a scratch `test_rls.tenant_items` table, so it changes only if the move breaks it.
- Base branch: `refactor/auth-module` from `feat/server-owned-auth`, PR targets it (same as SHIP-267).
- Users move to auth, with lazy personal workspace creation (Requirement 5) and one-way `identity → auth` imports.

## Status

in progress
