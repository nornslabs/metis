# PRD: feat-postman-api-collection

Linear: SHIP-269 · https://linear.app/heimdallabs/issue/SHIP-269/postman-api-collection-environments-and-mcp-server

## Problem / Goal

The Metis v1 API surface (auth, workspaces, settings, health) is stable, but there is no runnable, shareable contract for it. A Postman collection with local and Compose environments gives the team a way to exercise the API by hand and a reference for the OpenAPI schema; the Postman MCP server wires the agent host into the same collection so an agent can inspect and update it.

Goal: add `.agents/postman/` (collection, two environments, README), keep the local files in sync with the published Norns Labs items, and confirm the Postman MCP server entry in `opencode.json` is enabled.

## User stories

1. As a developer, I want to import the Metis API collection into Postman and run it against the local stack, so that I can smoke-test the API without curl.
2. As a developer, I want a Compose environment that points at `http://api:8000`, so that the same collection runs inside the container stack.
3. As an agent, I want the Postman MCP server enabled in `opencode.json`, so that I can look up the collection and keep it in sync with the API.

## Requirements

- `.agents/postman/metis-api.collection.json` — Postman Collection v2.1.0 covering every v1 route (health, auth, workspaces, settings), with a prerequest script that sets `X-Metis-Client`, the session cookie and the workspace header from variables.
- `.agents/postman/environments.local.json` — `baseUrl` defaults to `http://localhost:8000`.
- `.agents/postman/environments.compose.json` — `baseUrl` defaults to `http://api:8000`.
- `.agents/postman/README.md` — documents the published items, the collection contents, the variables, the prerequest script and the RFC 7807 error format.
- `opencode.json` — Postman MCP server at `https://mcp.postman.com/minimal`, enabled.
- The local files are kept in sync with the published collection and environments in the Norns Labs workspace.

## Out of scope

- Publishing the collection to Postman (done manually; the README records the published IDs).
- Running monitors, mocks or examples.
- The web app's API client (SHIP-222).

## Touches

- `.agents/postman/` (new)
- `opencode.json` (already present; verify)

## Dependencies

- None. The API routes and `opencode.json` entry already exist on `main`.

## Acceptance criteria

- `.agents/postman/` contains the collection, both environments and the README.
- The collection imports cleanly in Postman and every v1 route is covered (health, auth, workspaces, settings).
- `opencode.json` has the Postman MCP server enabled.
- The README documents the variables, prerequest script and error format.

## Status

draft