# Exa MCP tools for research specialists

## Goal

Give the Researcher, Scorer and Advisor authenticated access to Exa's hosted MCP tools using the Exa key saved for the run's workspace.

## Design

- Keep Exa transport in `adapters/mcp/exa.py` and use the shared streamable HTTP session helper.
- Load MCP tools for one run with `langchain-mcp-adapters`; send the workspace key only in the `x-api-key` header.
- Expose `web_search_exa` and `web_fetch_exa` to Researcher, and only `web_search_exa` to Scorer and Advisor.
- Normalize search results to `ResearchHit {url, title, published_at, snippet, source="exa"}`. Limit searches to 10 results and fetched content to 4,000 characters.
- Bound calls to 20 seconds, retry rate-limit and server failures twice with backoff, and map all upstream failures to `UpstreamError` with safe Exa reason metadata.
- Cache successful identical tool calls in Redis under the run ID for one hour. Publish one `tool_call` event for every invocation with only its query and result count.

## Failure behavior

- Missing workspace key remains `provider.not_configured` from the identity service.
- Exa's `(401)` MCP tool error becomes `provider.upstream_error` with `meta {provider: "exa", reason: "unauthorized"}`.
- Other tool and transport errors use the safe shared reason mapping; raw upstream text and credentials are not returned or logged.

## Verification

Exercise MCP loading, result normalization and bounds, caching, events and error mapping against the in-process fake Exa server. No real Exa requests are made.

## Current graph boundary

The graph currently uses stub specialists. This module provides run-scoped tools and allow-lists for the real specialist nodes; wiring those nodes is a separate graph implementation step.
