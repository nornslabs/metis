Status: ready-for-agent

# SHIP-220: LLM Gateway with OpenAI-Compatible Adapter

## Problem Statement

Metis needs to call an LLM while running agent work in its background worker. Workspaces bring their own OpenAI-compatible endpoint, API key, and model, and SHIP-217 already stores those credentials encrypted. The server currently has an adapter that can list models to test a saved key, but it cannot make chat calls and there is no provider port for agent code to depend on.

Without a gateway boundary, agent code would need to know how credentials are loaded and how a particular provider is called. That would make provider changes harder and risks exposing workspace secrets beyond the code that needs them.

## Solution

Add an LLM provider port and an OpenAI-compatible adapter that can make chat model calls using the current workspace's saved credentials. Keep credential retrieval behind the identity service and provider-specific behavior behind the adapter. Agent code should consume the port rather than construct provider clients or access saved keys directly.

## User Stories

1. As a workspace member running an agent workflow, I want the workflow to use my workspace's configured LLM endpoint and model, so that Metis performs work using my provider account.
2. As a workspace member, I want an agent run with no saved LLM key to fail with the existing clear `provider.not_configured` error, so that I know to configure a key before retrying.
3. As a workspace member, I want an agent run to use only the credentials saved for its workspace, so that another workspace's key is never used for my work.
4. As a workspace member, I want the gateway to send my configured model and key to my OpenAI-compatible endpoint, so that compatible hosted and local providers can serve agent calls.
5. As a workspace member, I want provider failures to become the existing safe provider errors, so that response bodies and credentials are not exposed in logs or error details.
6. As an agent developer, I want agent code to depend on an `LLMProvider` port, so that I can use a fake provider in tests and change adapters without rewriting agent behavior.
7. As an agent developer, I want the port to support asynchronous chat calls, so that it fits the worker's async runtime.
8. As an operator, I want LLM calls to use the shared provider timeout and HTTP behavior, so that an unavailable endpoint cannot hold a worker indefinitely.
9. As a workspace owner, I want agent LLM usage accounted against my configured run budget, so that a run stops before exceeding the spend limit.
10. As a workspace owner, I want the configured step limit applied to agent calls, so that a run cannot continue indefinitely.
11. As a maintainer, I want the existing model-list check to continue working when the adapter gains chat support, so that SHIP-217's provider-key test remains valid.
12. As a maintainer, I want adapter tests to use a fake HTTP transport and gateway tests to use a fake port, so that no test spends real tokens or calls a real provider.

## Implementation Decisions

- Add the `LLMProvider` interface in the core ports layer. Keep the interface provider-neutral and limited to the async chat/model operations needed by the agent graph; agent code must not import the concrete adapter or a vendor integration package.
- Extend the existing OpenAI-compatible adapter, preserving model listing and adding chat completion support for its configured `base_url`, API key, and model.
- Load credentials through the public identity module surface (`get_key_for_use`) for the active workspace. Do not read the provider-key table, decrypt secrets, or cache plaintext credentials in agent code.
- Keep all LLM network calls in worker-side execution. Request handlers must not invoke the gateway.
- Reuse shared provider HTTP behavior where compatible: bounded calls, no redirects, and safe mapping to `UpstreamError` metadata (`provider` and a non-sensitive reason). Never include API keys, authorization headers, or upstream response bodies in logs or errors.
- Use the already-installed LangChain OpenAI integration for compatibility with the LangGraph agent stack; do not add a second provider SDK or a second OpenAI-compatible adapter.
- Preserve the existing credential contract: the stored workspace `base_url` and model select the provider target; the API key is bearer authentication. Local HTTP endpoints remain governed by the existing development-only validation rule.
- Enforce the existing `run_budget_usd` and `max_steps` workspace settings for agent calls through the gateway. Keep accounting tied to the active run and workspace; do not introduce a separate budget configuration.
- Do not add retries/fallback policy, model discovery UI, or agent prompts.

## Testing Decisions

- Tests should verify externally observable port/adapter behavior, not internal helper calls.
- Test the adapter against an `httpx.MockTransport` or equivalent fake transport: correct chat request path, bearer authentication, configured model, supported request/response fields, and preservation of the existing model-list operation.
- Cover successful chat responses and safe error outcomes for unauthorized credentials, unreachable endpoints, timeouts, unsuccessful statuses, and malformed responses. Assert secrets and upstream bodies are absent from errors and logs.
- Test gateway credential lookup with a session scoped to a workspace: configured credentials reach only the provider adapter; missing credentials produce `provider.not_configured`; the gateway does not expose or log plaintext credentials.
- Test that usage from completed provider calls is attributed to the active workspace/run and that calls stop when the configured budget or step limit is reached.
- Test the consumer through the `LLMProvider` port using a fake implementation, proving agent-side code is decoupled from the concrete adapter and makes no real provider calls.
- Prior art: `server/tests/modules/identity/test_provider_keys_api.py` exercises provider calls through the FastAPI app with an overridden HTTP client factory. Follow its fake transport and database fixture conventions.

## Out of Scope

- Building or changing the LangGraph agent graph, specialist prompts, tools, or workflow stages.
- Exa or other provider adapters, fallback between providers, routing among models, or provider selection UI.
- Settings APIs or web UI for keys and models; those belong to SHIP-217/SHIP-219.
- Retries, rate limiting, caching, streaming responses, and model capability discovery beyond the existing list-model check.
- Calling the LLM from HTTP request handlers.

## Further Notes

- Source context: SHIP-217 records that SHIP-220 extends `adapters/llm.py` with chat calls and introduces the `LLMProvider` port. `server-context.md` names the OpenAI-compatible `ChatOpenAI` adapter as the MVP implementation and the agent graph as its consumer.
- The repo architecture requires every LLM call to be metered against the workspace budget, but it does not define a pricing source for arbitrary OpenAI-compatible endpoints. The implementation must establish how provider usage maps to USD before it can reliably enforce `run_budget_usd`; do not imply every compatible endpoint supplies comparable cost data.
- The supplied issue reference was not available as a local ticket, so this spec synthesizes the recorded repository decisions and the issue title. Confirm any additional acceptance criteria from the source ticket before implementation if they differ from this repo context.
