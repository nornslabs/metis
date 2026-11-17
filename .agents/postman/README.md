# Metis API — Postman Artifacts

This directory holds the Metis API collection and environments. They are also published to the **Norns Labs** Postman workspace.

## What's in Norns Labs (created 2026-11-16)

| Item | Name | ID | UID |
|------|------|----|-----|
| Collection | Metis API | `ac2ed807-72b5-43d1-9f00-e0bdac14b4bf` | `20411915-ac2ed807-72b5-43d1-9f00-e0bdac14b4bf` |
| Environment | Local (host) | `568ea643-cc80-4d36-a051-ab483b8509bd` | `20411915-568ea643-cc80-4d36-a051-ab483b8509bd` |
| Environment | Compose (container) | `e1f89bc7-2b32-487e-91f3-0b390389dbcb` | `20411915-e1f89bc7-2b32-487e-91f3-0b390389dbcb` |

Workspace: `b3aaa4ee-afe7-46dd-bd1c-3f9fb3cd7cd3` (Norns Labs, team, public)

## Collection contents

6 folders, 28 requests:

| Folder | Requests |
|--------|----------|
| Health | `GET /`, `GET /v1/health` |
| Auth | `GET /v1/auth/providers`, `GET /v1/auth/me`, `GET /v1/auth/google/login`, `GET /v1/auth/google/callback`, `POST /v1/auth/logout`, `POST /v1/auth/logout-all` |
| Workspaces | `GET /v1/workspaces`, `POST /v1/workspaces`, `GET /v1/workspaces/current` |
| Settings | `GET /v1/settings`, `PATCH /v1/settings`, `PUT /v1/settings/keys/:kind`, `DELETE /v1/settings/keys/:kind`, `POST /v1/settings/keys/:kind/test` |
| Ideas | `POST /v1/ideas`, `GET /v1/ideas`, `GET /v1/ideas/{idea_id}`, `PATCH /v1/ideas/{idea_id}`, `DELETE /v1/ideas/{idea_id}` |
| Runs | `POST /v1/ideas/{idea_id}/runs`, `GET /v1/ideas/{idea_id}/runs`, `GET /v1/runs/{run_id}`, `POST /v1/runs/{run_id}/resume`, `POST /v1/runs/{run_id}/cancel`, `GET /v1/runs/{run_id}/events` |

## Variables

| Variable | Default | Notes |
|----------|---------|-------|
| `baseUrl` | `http://localhost:8000` | API root. Switch to `http://api:8000` with the Compose environment. |
| `workspaceId` | *(blank)* | `X-Workspace-Id` header; blank uses the caller's personal workspace. |
| `sessionToken` | *(blank)* | Session cookie value (from `/v1/auth/google/callback`), without the `metis_session=` prefix. |
| `SESSION_COOKIE_NAME` | `metis_session` | Cookie name. |
| `keyKind` | `llm` | Provider kind: `llm` or `exa`. |
| `ideaId` | *(blank)* | Idea UUID for path parameters. |
| `runId` | *(blank)* | Run UUID for path parameters. |

## Prerequest script

The collection's prerequest script auto-applies, per request:

- `X-Metis-Client: web` on POST/PUT/PATCH/DELETE (CSRF).
- `Cookie: metis_session=<token>` when `sessionToken` is set.
- `X-Workspace-Id: <id>` when `workspaceId` is set.

## Auth note

Google sign-in requires `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in `.env`. When unset (the local default), `/v1/auth/providers` returns `[]` and signed-in routes return `401 auth.not_signed_in`. The collection's error examples reflect this.

## Local files

- `metis-api.collection.json` — Postman Collection v2.1.0 (mirror of the published collection).
- `environments.local.json` — Local (host) environment.
- `environments.compose.json` — Compose (container) environment.

These are kept in sync with the published items so the collection can be re-imported if needed.

## Error format

RFC 7807 `application/problem+json`:

```json
{
  "type": "http://localhost:8000/errors/auth.not_signed_in",
  "title": "Not Signed In",
  "status": 401,
  "code": "auth.not_signed_in",
  "detail": "Not signed in",
  "request_id": "01H...",
  "retryable": false
}
```

## References

- `server-context.md` — auth, modules, API conventions, error catalog.
- `project-overview.md` — Metis product scope.