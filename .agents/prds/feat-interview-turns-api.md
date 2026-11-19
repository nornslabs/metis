# PRD: feat-interview-turns-api

Linear: SHIP-270 · https://linear.app/heimdallabs/issue/SHIP-270/interview-turns-api

Milestone: M3 — Interview and discovery. Branch: `feat/interview-turns-api`. Blocks SHIP-239 (`feat-web-interview-research`). Related: SHIP-236 (`feat-interviewer`).

## Problem / Goal

The Interviewer stores every turn in `ideas.interview_turns` (SHIP-236), but no route returns them, and the run event stream replays questions (`interrupt`) without the user's answers. After a reload the web interview chat (SHIP-239) could show the pending question but none of the earlier questions and answers.

Goal: `GET /v1/ideas/{idea_id}/interview` returns the idea's interview turns, oldest first, so the web can rebuild the conversation. Server only; the web change is SHIP-239.

## User stories

1. As a web client, I want the idea's interview turns in order, so that I can rebuild the conversation after a reload.
2. As a web client, I want an open question to have `answer: null`, so that I can tell which question is still waiting.
3. As a web client, I want each turn to name its run, so that I can tell a clarification asked during research from an interview question.
4. As a web client, I want each turn to say whether it was asked or noted, so that I can show only what the user actually saw.
5. As a web client, I want an idea with no turns to return an empty list, not an error, so that a fresh idea needs no special case.
6. As a user, I want turns from every run of my idea in one list, so that a retried run shows the whole history.
7. As a workspace member, I want to read the turns of any idea in my workspace, so that teammates see the same conversation.
8. As a user of another workspace, I want a 404 for an idea that is not mine, so that nothing leaks across workspaces.
9. As a user, I want a 404 for an archived or unknown idea, so that the route behaves like the other idea routes.
10. As a signed-out caller, I want a 401, so that the route is private like every `/v1` route.
11. As a web developer, I want the route in the OpenAPI schema, so that `gen:api` gives me a typed client.
12. As a maintainer, I want the route to go through the ideas service, so that the controller stays thin.

## Requirements

1. **Route.** `GET /v1/ideas/{idea_id}/interview` in the ideas controller, under the existing `/ideas` router, behind the session cookie and `X-Workspace-Id` like the other idea routes. Response model: a new `InterviewTurnList` DTO `{items: [InterviewTurn]}`; no pagination (an interview has at most 8 asked turns per run plus noted turns).
2. **Turn shape.** The existing `InterviewTurn` DTO unchanged: `id`, `idea_id`, `run_id`, `topic`, `source` (`asked` | `noted`), `question`, `answer` (`null` while open). Order is the uuid7 `id`, oldest first (the table has no `position`; the `created_at` column is not exposed; Resolved 1).
3. **Service.** New `service.interview.list_interview(session, workspace_id, idea_id)`: checks the idea (`get_idea` → `IdeaNotFoundError`, so a foreign, archived or unknown idea is `404 idea.not_found`), then returns `list_turns`. The controller only calls the service.
4. **Empty list.** An idea with no turns returns `200 {items: []}`.
5. **Scope.** The existing repo query already filters by `workspace_id` and relies on RLS; no migration.
6. **OpenAPI.** Regenerate `web/lib/api/schema.d.ts` with `npm run gen:api` (CI drift check).
7. **Docs sync.** `server-context.md`: add the route to the API list. No `architecture.md` change.

## Out of scope

- Any web change (SHIP-239).
- Writing or editing turns; coverage or brief endpoints.
- Publishing answers as run events.
- Pagination, filtering by run or source.
- New migration or index.

## Touches

- `server/metis/modules/ideas/controller/` (interview route), `service/interview.py`, `dto/` (`InterviewTurnList`, export)
- `server/tests/modules/ideas/` (new route test)
- `web/lib/api/schema.d.ts` (regenerated)
- `.agents/ctx/server-context.md`
- `.agents/progress-tracker.md`

## Dependencies

- `feat-interviewer` (SHIP-236): done (`ideas.interview_turns`, `list_turns`).
- `feat-ideas-crud` (SHIP-218): done.

## Testing

One seam, the existing one: HTTP tests on the ideas routes with real Postgres and a session-cookie sign-in (`tests/modules/ideas/test_ideas_api.py` style, helpers in `idea_helpers.py`). Turns are seeded through the public ideas service (`open_question`, `answer_question`, `save_interview_turn`), not by hand. Tests check external behavior only:

- Turns come back oldest first with `answer: null` for an open question.
- Turns of two runs of the same idea appear in one list with their `run_id`.
- `asked` and `noted` turns both appear with the right `source`.
- No turns → `200` with an empty list.
- Another workspace's idea, an archived idea and a random id → `404 idea.not_found`.
- No session → `401`.

The route-table test (`test_route_auth.py`) already fails a route that forgets auth. `uv run ruff check`, `mypy`, `pytest` and `lint-imports` pass; the web schema drift check passes.

## Acceptance criteria

- [x] `GET /v1/ideas/{id}/interview` returns every turn of the idea, oldest first, with `answer: null` for an open question.
- [x] An idea without turns returns an empty list.
- [x] A foreign, archived or unknown idea is `404 idea.not_found`; no session is `401`.
- [x] The route is in the OpenAPI schema and `web/lib/api/schema.d.ts` is regenerated.
- [x] `server-context.md` lists the route.
- [x] `uv run ruff check`, `uv run mypy`, `uv run pytest` pass.

## Open questions

None open.

## Resolved (user, 2026-11-19)

1. Turn fields: return the existing `InterviewTurn` as is (`id`, `idea_id`, `run_id`, `topic`, `source`, `question`, `answer`). `created_at` from the issue is left out; order is the contract. The web shows only `asked` turns.

## Status

done
