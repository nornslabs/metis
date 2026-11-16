# PRD: feat-llm-gateway

Linear: SHIP-220 · https://linear.app/heimdallabs/issue/SHIP-220/14-llm-gateway-with-openai-compatible-adapter

Milestone: M2 — Ideas and agent run engine. Branch: `feat/llm-gateway`.

## Problem / Goal

A workspace can save and test its own OpenAI-compatible LLM key (SHIP-217), but nothing can chat with it. The agent graph (SHIP-223) and every specialist need one place to get a chat model for the current workspace, and every call must leave a usage record so the run budget (SHIP-237) can be enforced later.

Goal: an `LLMProvider` port, an OpenAI-compatible adapter on `langchain-openai` `ChatOpenAI`, and an agent-side gateway that builds a chat model from the workspace's saved credentials, records tokens (and cost when a price is known) for each call in a new usage table, and maps provider failures to the existing safe provider errors.

## User stories

1. As an agent specialist, I want a chat model for my workspace from one gateway call, so that I never handle keys or provider clients.
2. As a workspace member, I want runs to use my saved `base_url`, model and key, so that Metis works on my own provider account.
3. As a workspace member, I want a run with no saved LLM key to fail with `provider.not_configured`, so that I know to add one.
4. As a workspace member, I want a run to use only my workspace's key, so that another workspace's key is never used (RLS + AAD).
5. As a developer, I want a `purpose` (e.g. `interview`, `score`) to pick the temperature, so that scoring is steadier than interviewing.
6. As a developer, I want agent code to depend on the `LLMProvider` port, so that tests use a fake model and the adapter can change.
7. As a developer, I want nothing outside `adapters/` to import `langchain-openai`, so that the vendor stays swappable.
8. As an operator, I want every completed call to write a `llm_usage` row (run, workspace, model, input and output tokens, cost), so that spend is visible and the budget can be enforced later.
9. As an operator, I want `cost_usd` null unless a price for the model is configured, so that Metis never invents a cost for an arbitrary endpoint.
10. As an operator, I want to set optional per-model prices in settings, so that cost is filled in when I know the rates.
11. As an operator, I want usage rows kept even when the run later fails, so that spend is never lost.
12. As a workspace member, I want an unauthorized key, rate limit, timeout, unreachable endpoint or provider 5xx to become `provider.upstream_error` with a safe reason, so that I can act on it.
13. As an operator, I want keys, headers, prompts and upstream bodies absent from errors and logs, so that a log leak leaks nothing.
14. As an operator, I want a call to give up after 60 s and retry twice on transient errors, so that a dead endpoint cannot hold a worker.
15. As an operator, I want Langfuse tracing when `LANGFUSE_*` is set and nothing when it is not, so that local runs need no extra setup.
16. As a maintainer, I want the SHIP-217 key test (`list_models`) to keep working, so that the settings page is not broken.
17. As a maintainer, I want tests with a fake OpenAI-compatible server and no real provider calls, so that CI spends no tokens.
18. As a maintainer, I want request handlers unable to call the gateway, so that invariant 1 holds.

## Requirements

1. **Port** `LLMProvider` in `core/ports.py` (new file; `server-context.md` Ports already names it): an async chat model that can bind tools and be invoked with messages (LangChain message types, which the agent graph already uses), plus `aclose`. Core imports no module and no vendor package other than the LangChain core types.
2. **Adapter** package `adapters/llm/` (the existing `adapters/llm.py` becomes a package; `OpenAICompatibleClient.list_models` keeps its import path and behaviour):
   - `openai_compat.build_chat_model(credentials, purpose, http_client?)` returns a `ChatOpenAI` (`base_url`, `api_key`, `model` from the credentials, `timeout=60`, `max_retries=2`, named constants; temperature by `purpose` from a small named table). It takes already-decrypted credentials as arguments and imports no module: an adapter must not import `identity`, so the issue's "adapter reads the key" step is split: the gateway reads the key, the adapter builds the model.
   - The `httpx` async client is injectable so tests route to a fake server.
   - Provider exceptions from `openai` are mapped to `UpstreamError` (`provider.upstream_error`, `meta {provider: "llm", reason}`), reasons `unauthorized`, `rate_limited`, `timeout`, `unreachable`, `server_error`, `bad_response`. Keys and upstream bodies never reach the error.
3. **Gateway** `agent/llm.py`:
   - `get_chat_model(session, workspace_id, run_id, purpose) -> LLMProvider`: reads credentials through `identity.get_key_for_use(session, workspace_id, "llm")` (missing → `ProviderNotConfiguredError`), builds the model through the adapter, attaches the usage callback, and caches the model per `(run_id, purpose)` for the run's life (`aclose` at run end).
   - The usage callback records `input_tokens`, `output_tokens` from the response's usage metadata after each call. If a provider returns no usage, the row is written with `0`/`0` and `cost_usd` null (never skipped).
   - The gateway holds credentials only to build the model; it does not store or log them.
4. **Usage table** `llm_usage(id uuid pk, run_id uuid not null, workspace_id uuid not null → workspaces ON DELETE CASCADE, model text not null, input_tokens int not null, output_tokens int not null, cost_usd numeric(12,6) null, created_at)` in the `ideas` schema (ideas owns workflow runs), RLS through `enable_tenant_rls`, index on `(workspace_id, run_id)`. Migration `0011_llm_usage`. `run_id` has no foreign key yet: the runs table arrives with SHIP-225, which adds it. Rows are written through an `ideas` service function (`record_llm_usage`), in its own short transaction on a worker session, so a failing run keeps them. The agent reaches the table only through that service.
5. **Cost**: optional setting `LLM_PRICES` (JSON, model id → `{input_per_million_usd, output_per_million_usd}`), read in `core/config.py`. A model with no entry gives `cost_usd = null`. No built-in price list.
6. **Langfuse**: when `LANGFUSE_*` are set, the gateway adds the Langfuse LangChain callback; otherwise nothing is added. Prompts and completions are never logged by Metis' own logger.
7. **Logging**: `llm.call` with `run_id`, `workspace_id`, `model`, token counts, `ok`, failure reason. Never keys, headers or prompts.
8. **Boundaries**: import-linter keeps `adapters` off modules and `core` off modules; a contract (or test) checks that only `adapters/llm/` imports `langchain_openai`/`openai`.
9. **Docs sync**: `server-context.md` (Ports, adapters list, `ideas` tables, `LLM_PRICES`, error reasons), `architecture.md` (invariant 6: calls metered into `llm_usage`; enforcement is SHIP-237), Notion LLD.

## Out of scope

- Budget and step-limit enforcement, rate limiting (SHIP-237, M7). Usage is recorded only.
- The agent graph, prompts, tools and stages (SHIP-223 and later); the runs table and API (SHIP-225).
- Exa and other adapters, native non-OpenAI adapters, fallback or routing between models.
- Streaming to the browser (the graph's stream handles tokens), model discovery, caching of responses.
- Any HTTP route; handlers must not call the gateway.
- Web settings page (SHIP-219).

## Touches

`server/metis/core/ports.py` (new), `server/metis/core/config.py`, `server/metis/core/errors.py` (reasons only), `server/metis/adapters/llm/` (package), `server/metis/agent/llm.py` (new), `server/metis/modules/ideas/` (`models`, `repo`, `service`, `__init__`), `server/migrations/versions/0011_llm_usage.py` (new), `server/pyproject.toml` + `uv.lock` (`langfuse` only if not present, via `uv`), `server/tests/` (adapter, gateway, migration, boundary), `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`.

## Dependencies

- `feat-provider-keys` (SHIP-217): done. `get_key_for_use`, `ProviderCredentials`, `OpenAICompatibleClient`.
- SHIP-209 (jobs, events, outbox): done (SHIP-211, 212, 213).
- `feat-ideas-crud` (SHIP-218): done; `ideas` schema grants and module exist.
- Blocks: SHIP-223 (agent graph), SHIP-226 (Exa MCP tools), SHIP-237 (budgets).

## Test seam

One seam, the gateway (`agent/llm.py`) against **real Postgres** (migrated to head, a session scoped to the workspace as a non-superuser role) and a **fake OpenAI-compatible server** through the injected `httpx` client (`MockTransport` serving `/chat/completions` and `/models`). This is the highest seam without a route, and the same fake-transport approach as `test_provider_keys_api.py`. A good test asserts only what a caller sees: the returned model's reply, the raised error, the stored rows, the request the fake server received.

Planned tests:

- Saved key → `get_chat_model(...).ainvoke` returns the fake reply; the fake server saw `Authorization: Bearer <key>`, the saved model and the right path under `base_url`; one `llm_usage` row with the reply's token counts for the run and workspace.
- No key saved → `provider.not_configured`; no HTTP call made.
- Workspace B cannot use workspace A's key; usage rows of A are invisible from B (RLS).
- Fake server 401 → `UpstreamError` reason `unauthorized`; 429 → `rate_limited`; 500 → `server_error`; malformed body → `bad_response`; connect error → `unreachable`; stalled server → `timeout`. Error text and logs contain no key and no body.
- A transient 500 then 200 succeeds (retry), writing one usage row.
- Usage missing from the reply → row with `0`/`0`, `cost_usd` null.
- `LLM_PRICES` entry → `cost_usd` computed; no entry → null.
- A call that fails still leaves earlier usage rows (own transaction).
- Same `(run_id, purpose)` reuses the cached model; `purpose` changes temperature in the request.
- `list_models` still passes its existing tests; `uv run lint-imports` passes with the vendor-import check.
- Consumers get a fake `LLMProvider` in other tests; no test calls a real provider.

## Acceptance criteria

- [x] A workspace with a saved key gets a working chat model; one without gets `provider.not_configured`.
- [x] Every completed call writes a `llm_usage` row tied to the run and workspace.
- [x] No vendor import (`langchain_openai`, `openai`) outside `adapters/`.
- [x] Provider failures surface as `provider.upstream_error` with a safe reason; no key or body leaks.
- [x] `cost_usd` is null unless a price is configured.
- [x] Tests above pass; `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run lint-imports` pass.
- [x] `server-context.md` and `architecture.md` updated.

## Open questions

None open.

1. ~~`run_id` has no table yet.~~ Resolved 2026-11-16: `run_id` is stored without a foreign key; SHIP-225 adds it when it creates the runs table.
2. ~~Error shape.~~ Resolved 2026-11-16: reuse `UpstreamError` (`provider.upstream_error`, `meta.reason`) and add the reasons `rate_limited` and `server_error`; no new `ProviderError`.
3. ~~Existing PR #32 / branch `feat/ship-220-llm-gateway`.~~ Resolved 2026-11-16: leave it unmerged; build on `feat/llm-gateway` from `main`, as AGENTS.md requires; close #32 once this PRD lands.

## Built differently from the wording above, on purpose

- The gateway is a class, `LLMGateway(workspace_id, run_id, ...)`, one per run, with `chat_model(session, purpose)` and `aclose()`, not a module-level `get_chat_model` with a global cache; the per-`(run_id, purpose)` cache lives on the instance, so there is no global state to leak between runs.
- `adapters/llm/chat.py` wraps `ChatOpenAI` in `OpenAICompatibleChat` so the port's `ainvoke` always returns an `AIMessage` and every provider failure is mapped in one place.
- `FailureReason` (`helpers/http.py`) gained `rate_limited` and `server_error`; `helpers/pricing.py` holds `ModelPrice` and `cost_usd`.
- Langfuse (`langfuse` added with `uv add`) is wired in `agent/tracing.py`.
- The vendor-import rule is an import-linter contract (`include_external_packages = true`, direct imports only).
- `tests/conftest.py` got an autouse fixture that turns off structlog's logger caching: the new gateway tests run before the auth tests and were the first to use the auth logger, which made `capture_logs` in `test_secrets_never_reach_the_logs` miss its events (an existing order dependence).

## Status

done
