# PRD: feat-provider-keys

Linear: SHIP-217 · https://linear.app/heimdallabs/issue/SHIP-217/11-provider-keys-and-settings-api

## Problem / Goal

Metis is free and every workspace brings its own keys: an OpenAI-compatible LLM endpoint (`base_url` + key + model) and an Exa key. Today a workspace has nowhere to save them, no way to check that they work, and no per-workspace run settings. The LLM gateway (SHIP-220), the Exa adapter and the web settings page (SHIP-219) are all blocked on this.

Goal: a workspace can save, test and remove its LLM and Exa keys, and read and update its run settings (`run_budget_usd`, `max_steps`). Keys are sealed with envelope encryption (`core/crypto.py`, workspace id as AAD), stored in `identity`, never returned or logged in plain text, and only decrypted through one service function for the LLM gateway and Exa adapter. Settings updates use optimistic concurrency (`version`, 409 on mismatch).

## User stories

1. As a workspace member, I want to save my OpenAI-compatible LLM key with its `base_url` and model, so that Metis can run agents on my own provider.
2. As a workspace member, I want to save my Exa key, so that Metis can research my ideas.
3. As a user, I want `GET /v1/settings` to show which keys are set, masked (`sk-…a1b2`), with their `base_url`, model and last test result, so that I can see what is configured without exposing secrets.
4. As a user, I want a key that is not set to appear as `null`, so that the settings page can prompt me to add it.
5. As a user, I want saving a key again to replace the old one, so that I can rotate keys.
6. As a user, I want replacing a key to clear its last test result, so that I never see "ok" for a key that was not tested.
7. As a user, I want to delete a key, so that Metis stops using it.
8. As a user, I want deleting a key that is not set to return 404, so that client bugs are obvious.
9. As a user, I want a "Test" button that makes one cheap call to my provider and tells me ok or the provider's error, so that I know my key works before I run anything.
10. As a user, I want a failed test to return a clear 502 problem (`provider.upstream_error`) naming what failed (unauthorized, unreachable, timeout, bad response), so that I can fix the key or URL.
11. As a user, I want testing a key that is not set to return a clear `provider.not_configured` error, so that I know to add it first.
12. As a user, I want the test to give up after 10 s, so that a dead endpoint does not hang the page.
13. As a user, I want the result of each test (`last_tested_at`, `last_test_ok`) stored, so that the settings page shows the key's health later.
14. As a user, I want a non-https `base_url` rejected with 422, so that my key is never sent in clear text.
15. As a developer running a local model, I want `http://localhost` / `127.0.0.1` allowed when `APP_ENV=development`, so that I can use Ollama or LM Studio.
16. As a user, I want an LLM key without `base_url` or `model`, or an Exa key with them, rejected with 422, so that each kind stores exactly what it needs.
17. As a user, I want an empty or oversized key rejected with 422, so that typos fail fast.
18. As a user, I want to update `run_budget_usd` and `max_steps` with `PATCH /v1/settings`, so that I control spend and agent length.
19. As a user editing settings in two tabs, I want a stale `version` to get 409, so that I never overwrite a newer change silently.
20. As a user, I want out-of-range settings rejected with 422, so that a typo cannot set an unlimited budget.
21. As a new workspace, I want default settings without saving anything, so that runs work right after I add keys.
22. As a member of workspace A, I want workspace B's keys and settings invisible and unusable to me, so that tenants stay isolated (RLS + AAD).
23. As the LLM gateway / Exa adapter, I want `get_key_for_use(kind)` to return the decrypted key (and `base_url`, model), so that I can call the provider; nothing else may call it.
24. As the LLM gateway, I want a missing key to raise `provider.not_configured`, so that a run fails with a clear message.
25. As an operator, I want keys never logged, never in error details and never in responses, so that a log leak does not leak keys.
26. As a maintainer, I want HTTP-level tests with the provider faked (round trip, masked output only, provider failure → 502, version conflict → 409, RLS isolation), so that regressions fail CI.

## Requirements

1. **Migration `0005_provider_keys`** (schema `identity`, grants to `metis_app` already cover `identity` via default privileges; verify):
   - Enum `identity.provider_kind` = `llm`, `exa`.
   - `identity.provider_keys(id uuid pk, workspace_id uuid not null → workspaces ON DELETE CASCADE, kind provider_kind not null, base_url text null, model text null, sealed jsonb not null, masked text not null, last_tested_at timestamptz null, last_test_ok boolean null, version int not null default 1, created_at, updated_at)`, unique `(workspace_id, kind)`.
   - `identity.workspace_settings(workspace_id uuid pk → workspaces ON DELETE CASCADE, run_budget_usd numeric(10,2) not null, max_steps int not null, version int not null default 1, updated_at)`.
   - `enable_tenant_rls` on both tables.
   - `sealed` holds the `SealedSecret` fields (`ciphertext`, `nonce`, `wrapped_key` base64, `key_version` int).
2. **Enum** `ProviderKind` (`llm`, `exa`) in `identity/schemas.py`, exported; listed in `server-context.md` Domain Primitives.
3. **Service** (`identity/service.py`, takes the caller's session, never commits, sets/restores RLS context like the existing functions):
   - `set_key(session, workspace_id, kind, value, base_url=None, model=None) -> ProviderKeyView`: validates input (see 5), `crypto.encrypt(value, workspace_id)`, stores `sealed` + `crypto.mask(value)`; upsert on `(workspace_id, kind)`; on replace bumps `version` and clears `last_tested_at`/`last_test_ok`.
   - `get_key_for_use(session, workspace_id, kind) -> ProviderCredentials` (frozen: `kind`, `api_key`, `base_url`, `model`): decrypts; missing → `ProviderNotConfiguredError` (`provider.not_configured`). Exported for the LLM gateway and Exa adapter only (documented); no route calls it directly.
   - `delete_key(session, workspace_id, kind)`: missing → `NotFoundError` (404).
   - `test_key(session, workspace_id, kind) -> KeyTestResult`: loads credentials, calls the LLM or Exa adapter (see 4), stores `last_tested_at` + `last_test_ok` (on failure too) and returns the result without raising, so the stored result survives (see the note under Open questions).
   - `get_settings(session, workspace_id) -> WorkspaceSettingsView` (defaults with `version: 0` when no row); `update_settings(session, workspace_id, patch, version)`: `version` mismatch → `ConflictError` (409); bumps `version`.
4. **Provider adapters** (`httpx.AsyncClient`, 10 s total timeout as a named constant, no vendor SDK). The call chain is always route → `identity.service.test_key` → adapter; the route never calls a provider or an adapter itself.
   - **LLM adapter** (`server/metis/adapters/llm.py`): an OpenAI-compatible client built from `base_url` + key with `list_models() -> list[str]` (`GET {base_url}/models`, `Authorization: Bearer <key>`); 2xx = key works. No tokens spent. This is the first piece of the LLM adapter; SHIP-220 (LLM gateway) extends it with chat calls.
   - **Exa MCP client** (`server/metis/adapters/mcp/exa.py`, on the shared `server/metis/helpers/mcp.py`): `check()` connects to Exa's hosted MCP server (`https://mcp.exa.ai/mcp`, key in `x-api-key`) and calls `web_search_exa` once with `numResults: 1`. Exa also serves keyless searches, so listing tools proves nothing; only a tool call checks the key. A bad key is a tool `isError` containing `(401)` → `unauthorized`. No `exa-py` (removed). The agents load the same server's tools in SHIP-226.
   - Both raise `UpstreamError` with a safe `detail`: `unauthorized` (401/403), `unreachable` (connect error / DNS), `timeout`, `bad_response` (other non-2xx or unparseable body). The key and the upstream body are never in `detail` or logs.
   - The service turns `UpstreamError` into a failed `KeyTestResult`. It does not check that the saved `model` appears in the list, because some proxies return partial lists.
   - The `httpx` transport is injectable (a FastAPI dependency passed into the service) so tests swap in `httpx.MockTransport`.
5. **Validation** (Pydantic request schemas + service):
   - `kind` path param must be `llm` or `exa` (else 422).
   - `llm`: `base_url` and `model` required; `exa`: both must be absent.
   - `base_url`: `https://` only; `http://` allowed only for host `localhost` / `127.0.0.1` / `::1` when `app_env == "development"`. Trailing slash normalised. Max length 2048.
   - `value`: stripped, non-empty, max 512 chars. `model`: non-empty, max 200.
   - Settings: `0 < run_budget_usd ≤ 100` (2 decimals), `1 ≤ max_steps ≤ 200`; defaults `2.00` / `50`.
   - Writes (PUT/DELETE keys, PATCH settings) require the `owner` role, else `PermissionDeniedError` (403).
6. **Routes** (`identity/api.py`, all on `CurrentWorkspaceDep`, thin handlers):
   - `GET /v1/settings` → `200 {keys: {llm: ProviderKeyView | null, exa: ProviderKeyView | null}, settings: {run_budget_usd, max_steps, version}}`.
   - `PUT /v1/settings/keys/{kind}` body `{value, base_url?, model?}` → `200 ProviderKeyView`.
   - `DELETE /v1/settings/keys/{kind}` → `204`.
   - `POST /v1/settings/keys/{kind}/test` → `200 ProviderKeyView` (ok) or 502 problem.
   - `PATCH /v1/settings` body `{version, run_budget_usd?, max_steps?}` → `200 settings` or 409.
   - `ProviderKeyView` = `{kind, base_url, model, masked, last_tested_at, last_test_ok, version, updated_at}`. No field ever carries plaintext or `sealed`.
7. **Errors**: add `ProviderNotConfiguredError` (`provider.not_configured`) to `core/errors.py`; reuse `UpstreamError` (`provider.upstream_error`, 502) as the issue's `ProviderError`, `ConflictError` (409), `NotFoundError`, `InvalidInputError`, `SecretDecryptError` (422). Update the `server-context.md` error table to the real class names.
8. **Logging**: log `provider_key.saved/deleted/tested` with `kind`, `ok`, failure reason; never the key, `sealed`, or upstream body.
9. **Docs sync**: `server-context.md` (identity contract: key/settings functions, `get_key_for_use` callers, routes, `ProviderKind`, probe rules, error table); `architecture.md` (invariant 1 exception for the key test, if approved).

## Out of scope

- Hosted keys, per-user keys, native non-OpenAI adapters (Anthropic, Gemini SDKs).
- The LLM gateway and Exa adapter themselves (SHIP-220 and later); only the probe lives here.
- Budget metering and enforcement of `run_budget_usd` / `max_steps` (they are only stored here).
- Web settings page (SHIP-219).
- MCP connection credentials (SHIP-231).
- Master-key rotation / re-encryption of stored keys.
- Rate limiting the test endpoint.

## Touches

`server/migrations/versions/0005_provider_keys.py` (new), `server/metis/modules/identity/models.py`, `repo.py`, `schemas.py`, `service.py`, `api.py`, `__init__.py`, `server/metis/adapters/llm.py` (new), `server/metis/adapters/mcp/exa.py` (new), `server/metis/helpers/{http,mcp,ids,validation,text}.py` (new `helpers` package; `ids.py` moved from `core`), `server/pyproject.toml` + `uv.lock` (`exa-py` removed, `mcp` added via `uv`), `server/metis/core/errors.py`, `server/tests/modules/identity/test_provider_keys_api.py` (new), `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`.

## Dependencies

- `feat-secret-encryption` (SHIP-215): done. `encrypt`, `decrypt`, `mask`, `SealedSecret`.
- `feat-jwt-auth` (SHIP-216): done. `CurrentWorkspaceDep`, request session, `metis_app` role.
- Blocks: SHIP-219 (web settings page), SHIP-220 (LLM gateway).

## Test seam

Agreed: one seam, the same as SHIP-216, **HTTP requests against the FastAPI app** (ASGI client, locally signed JWTs, real Postgres migrated to head, request session as a non-superuser role, `identity` tables truncated per test). The provider client factory is overridden: LLM calls go to an `httpx.MockTransport`, Exa calls go to an in-process fake Exa MCP server (`FastMCP` from the `mcp` SDK, `tests/modules/identity/fake_exa_mcp.py`) through `httpx.ASGITransport`, so no real provider calls. `get_key_for_use` has no route, so its round trip is checked with one service-level call on a session scoped like the request (same pattern as `test_identity_service.py`).

Planned tests:

- PUT llm key → 200, response has `masked` and no plaintext; GET shows it; the raw `sealed` column does not contain the plaintext; `get_key_for_use` returns the plaintext, `base_url`, model.
- GET with nothing set → both keys `null`, default settings.
- PUT again → `version` 2, old test result cleared, new key decrypts.
- DELETE → 204, GET shows `null`; DELETE again → 404.
- Validation: `http://example.com` → 422; `http://localhost:11434/v1` → 200 in development, 422 otherwise; llm without `model` → 422; exa with `base_url` → 422; empty value → 422; unknown kind → 422.
- Test endpoint: mock 200 → 200 `last_test_ok: true`; mock 401 → 502 `provider.upstream_error`, detail mentions unauthorized, no key in body; mock timeout / connect error → 502; subsequent GET shows `last_test_ok: false`; no key set → `provider.not_configured`.
- PATCH settings with `version: 0` on a new workspace → 200, version 1; current version → 200, version +1; stale version → 409 `common.conflict`; out-of-range → 422.
- A `member` (not owner) PUT/DELETE/PATCH → 403 `auth.forbidden`; GET and test → allowed.
- Isolation: keys saved in workspace A are `null` from workspace B; `get_key_for_use` from B → not configured.
- No response body in any test contains the plaintext key.

## Acceptance criteria

- [x] Saved keys are stored encrypted (envelope, workspace AAD); no response ever contains plaintext.
- [x] `GET /v1/settings` returns masked keys and settings.
- [x] `POST …/test` returns ok or a clear 502 provider error within 10 s, and records the result.
- [x] Settings updates use optimistic concurrency (409 on stale `version`).
- [x] `base_url` is https, except localhost in development.
- [x] Both tables are RLS-scoped; another workspace cannot see or use the keys.
- [x] Tests above pass; `uv run ruff check`, `uv run mypy`, `uv run pytest` pass.
- [x] `server-context.md` (and `architecture.md` if invariant 1 changes) updated.

## Open questions

None open.

1. ~~Invariant 1 vs. the test endpoint.~~ Resolved 2026-11-14: handlers never call providers. `POST …/test` calls `service.test_key`, which uses the LLM adapter (`list_models`) or the Exa adapter (`check`). One bounded call, 10 s timeout, and the LLM check spends no tokens. Invariant 1 in `architecture.md` gets this wording when the PRD is implemented.
2. ~~Settings defaults and bounds.~~ Resolved 2026-11-14: defaults `run_budget_usd = 2.00`, `max_steps = 50`; bounds `0 < run_budget_usd ≤ 100`, `1 ≤ max_steps ≤ 200` (named constants). No row until the first PATCH; GET returns defaults with `version: 0`; PATCH with `version: 0` creates the row.
3. ~~Write access.~~ Resolved 2026-11-14: owners only for PUT/DELETE keys and PATCH settings (`PermissionDeniedError`, 403, for members); any member may GET settings and test a key.
4. ~~Test seam.~~ Resolved 2026-11-14: the single HTTP seam above, with the LLM and Exa adapters' transport replaced by `httpx.MockTransport`, plus one service-level check for `get_key_for_use`.

Decided (not open): a failed test must still store `last_test_ok = false`, but the request session rolls back on any exception. So `test_key` records the result and returns a `KeyTestResult(ok, reason, key)` instead of raising; the route returns the 502 RFC 7807 problem (`provider.upstream_error`) as a response, built by the existing error handler helper, without raising. The session then commits as normal. Tests assert the stored result after a failure.

## Review follow-ups (2026-11-14)

Applied after the two-axis code review:

- The 10 s cap is now a total cap: `adapters/http.send` wraps the call in `asyncio.timeout(PROVIDER_TIMEOUT_SECONDS)`. Before, `httpx`'s timeout applied to each phase separately, so a slow endpoint could run past 10 s. A new test checks it.
- `Settings.is_development` replaces the service's hardcoded `"development"` string.
- `_saved_key` is the single place that raises `ProviderNotConfiguredError`. Removed the unused `KeyTestResult.ok`. The settings changes are built only on the update path.
- Test cleanup: one `key_for_use` helper, and a clearer `add_member_directly` docstring.

Built differently from the wording above, on purpose:

- `kind` is `text` with a CHECK constraint, not a Postgres enum, matching `identity.members.role`; adding a kind is then a plain migration.
- `set_key`, `delete_key` and `update_settings` take the caller's `Membership` (workspace + role) instead of `workspace_id`, so the service does the owner-only check. `get_settings` is `get_settings_overview` and returns keys + settings.
- `KeyTestResult` is `(key, error)`. The failure reason is in the 502's `meta.reason` (`unauthorized`, `unreachable`, `timeout`, `bad_response`); `detail` is a fixed safe sentence.
- Deleting a missing key returns `provider.key_not_found` (404) through a new `ProviderKeyNotFoundError`. The generic `NotFoundError` code is `common.route_not_found`, which is wrong for this case.
- `base_url` also rejects credentials, a query and a fragment. `PATCH /v1/settings` rejects unknown fields and a body that changes nothing.
- The shared HTTP test fixtures moved into `tests/modules/identity/conftest.py` + `api_helpers.py`.

Not changed (decided earlier):

- `test_key` returns its `UpstreamError` instead of raising it, so the failed result still commits (see the note under Open questions).
- Tests stay at the agreed HTTP seam; there are no per-layer unit tests.
- There is no `core/ports.py` yet. The LLM gateway (SHIP-220) adds the `LLMProvider` port, and the adapters will implement it.
- A key that can't be decrypted during a test returns 422 `crypto.decrypt_failed` and records nothing; the user re-enters it.

Follow-up for later: in production `base_url` can be any https host, including private addresses, because the key test calls the URL from the server. Consider blocking private IP ranges before hosting publicly.

## Exa through MCP (2026-11-14)

Changed after review, at the user's request: Exa is reached through its hosted MCP server, not a hand-written HTTP adapter.

- `adapters/exa.py` (now `adapters/mcp/exa.py`) is `ExaMcpClient`, built on the new shared `helpers/mcp.py` (`open_mcp_session`, which Linear/Notion MCP can reuse later).
- `helpers/http.py` (was `adapters/http.py`) hands out a `ClientFactory` (`provider_http_factory`), because the MCP SDK sends the client's headers, so the key must be set when the client is created. `capped()` gives every provider call a 10 s total cap.
- The check calls `web_search_exa` once with 1 result. This was confirmed against the real server: `query` and `objective` are required, and a bad key returns a tool error `(401)` instead of falling back to keyless mode.
- `exa-py` was removed (`uv remove exa-py`) and `mcp` added (`uv add mcp`).
- Tests: Exa cases run against a fake Exa MCP server in-process (ok, bad key, HTTP 401, tool error, unreachable, timeout).
- Linear: SHIP-226 was rewritten to load Exa's MCP tools for the Researcher, Scorer and Advisor. No new issue: it already covered "Exa for the agents", and it stays on M3 behind the LLM gateway.

## Helpers package (2026-11-14)

At the user's request, generic stateless code moved to a new `server/metis/helpers/` package, and the rule for it is in `architecture.md` (System Boundaries):

- `helpers/http.py` and `helpers/mcp.py` (from `adapters/`). `adapters/` now holds only vendor wrappers (`llm.py`, and `mcp/exa.py` in the `adapters/mcp/` subfolder for MCP-reached providers).
- `helpers/ids.py` (`uuid7`, from `core/ids.py`; its tests moved to `tests/helpers/`).
- `helpers/validation.py` → `validate_input` (from identity `service._validate`).
- `helpers/text.py` → `strip`, `strip_to_none` (from identity `schemas`).
- Unit tests for the two new helpers are in `tests/helpers/`.

Left in place: `repo.rls_context` (DB infrastructure), `seal_to_json`/`seal_from_json` (secret storage format), `_check_base_url` and the email checks (identity product rules), and the test helpers under `tests/`.

## Status

done
