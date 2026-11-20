# PRD: feat-scoring-module

Linear: SHIP-227 · https://linear.app/heimdallabs/issue/SHIP-227/23-scoring-module-rubric-score-runs-and-bands

Milestone: M4 — Scoring and advice. Branch: `feat/scoring-module`. Blocked by SHIP-218 (`feat-ideas-crud`, done). Blocks SHIP-240 (Scorer specialist).

## Problem / Goal

Metis promises a score out of 100 with a reason, evidence and confidence for each of six parameters (project overview, success criterion 4). Nothing stores a score today: there is no `scoring` module, no rubric, `ideas.current_score` is never written, and nothing turns six raw marks into a total and a band (`build`, `promising`, `advise`).

Goal: add the `scoring` module (own `scoring` schema) that holds the fixed rubric (versioned), stores **immutable score runs** with six per-parameter scores (raw mark, weighted points, reason, confidence, evidence), computes the total and band, announces the result through the outbox, keeps `ideas.current_score` in step, and exposes history, latest score and a score run through the API. The Scorer agent (SHIP-240) will call the service; no LLM is involved here.

## User stories

1. As a founder, I want my idea scored out of 100, so that I can compare it with my other ideas.
2. As a founder, I want to see all six parameters (problem severity, uniqueness, market demand, value, feasibility, timing) with their own marks, so that I know what drives the total.
3. As a founder, I want each parameter's weight shown with its mark, so that I understand why uniqueness moves the total more than timing.
4. As a founder, I want a written reason for every parameter, so that a mark is never a bare number.
5. As a founder, I want evidence links, titles and quotes behind each parameter, so that I can check the claim myself.
6. As a founder, I want a confidence for each parameter, so that I can tell a solid mark from a guess.
7. As a founder, I want a parameter with no evidence to say so and to carry a low confidence, so that Metis never presents a guess as a fact.
8. As a founder, I want a band (`build`, `promising`, `advise`), so that I know at a glance whether to build, refine or rethink.
9. As a founder, I want 75 to count as "build" and 74 as "promising", 55 as "promising" and 54 as "advise", so that the edges are predictable.
10. As a founder, I want the total computed by Metis from the six marks, so that an agent can never state a total that disagrees with its marks.
11. As a founder, I want every score kept, so that I can see how my idea's score moved over time.
12. As a founder, I want old scores to stay exactly as they were, so that a past score can still be explained.
13. As a founder, I want a rescore to add a new score run, not change the old one, so that history is honest.
14. As a founder, I want to open the latest score of an idea, so that I see the current verdict without re-running anything.
15. As a founder, I want the score history newest first, so that I read the story from now backwards.
16. As a founder, I want to open any past score run with all its parameters, so that I can read the reasons it was given.
17. As a founder, I want to see what triggered a score (`manual`, `scheduled`, `signal`), so that I know whether I asked for it or the market changed.
18. As a founder, I want to see which rubric version a score used, so that scores made under different rubrics are not confused.
19. As a founder, I want to compare two score runs parameter by parameter, so that I see what improved after I revised the idea.
20. As a founder, I want the idea's current score to match its latest score run, so that lists and headers never show a stale number.
21. As a founder, I want an archived idea's scores hidden like the idea, so that archive behaves the same everywhere.
22. As a workspace member, I want to read the scores of any idea in my workspace, so that the team sees the same verdict.
23. As a founder, I want my scores hidden from other workspaces, so that my ideas stay private.
24. As the Scorer agent (SHIP-240), I want to read the rubric (parameters and weights), so that my prompt and my marks use the same scale.
25. As the Scorer agent, I want to submit six parameters and get back the stored score run with total and band, so that I do not compute anything myself.
26. As the Scorer agent, I want a submission with a missing, unknown or duplicate parameter refused with a clear message, so that I can fix it and resubmit.
27. As the Scorer agent, I want a mark outside 0–10, a confidence outside 0–1 or an empty reason refused, so that bad output never reaches the database.
28. As the Scorer agent, I want a parameter with no evidence refused unless I say so explicitly, so that I am forced to either cite or admit it.
29. As the Scorer agent, I want to tie a score run to my workflow run, so that it can be traced to the run that made it.
30. As a later specialist (Advisor, Architect), I want to read the latest score and the diff of two scores through the scoring service, so that I can build on them.
31. As a downstream consumer (notifications, market watch), I want a `ScoreComputed` event with the new total, band and the previous total, so that I can react to a change without querying.
32. As a developer, I want the event written in the same transaction as the score run, so that it exists only if the score does.
33. As a developer, I want no service function or SQL grant that updates or deletes a score run, so that immutability is enforced, not just promised.
34. As a developer, I want the weight math and the banding in pure, unit-tested helpers, so that the rubric cannot drift.
35. As a developer, I want RLS on every scoring tenant table, so that a missed `WHERE workspace_id` cannot leak data.
36. As a developer, I want the scoring module reached only through its `__init__.py`, so that module boundaries hold.
37. As a developer, I want the scoring routes in the OpenAPI schema, so that the typed web client gets them.

## Requirements

### Schema (migration `0017_scoring`, schema `scoring`)

1. `scoring.rubric_versions`: `id` (integer primary key, the version number), `weights` (jsonb: `{param: weight}`), `created_at`. Seeded with version 1: `problem_severity` 25, `uniqueness` 25, `market_demand` 15, `value` 15, `feasibility` 10, `timing` 10. A global table (no `workspace_id`, no RLS); `metis_app` has `SELECT` only. The weights summing to 100 cannot be a CHECK on jsonb; a migration test checks it instead.
2. `scoring.score_runs`: `id` (uuid7), `workspace_id`, `idea_id` (FK `ideas.ideas`, cascade), `run_id` (FK `ideas.workflow_runs`, cascade), `rubric_version_id` (FK `rubric_versions`), `trigger` (`ScoreTrigger`: `manual`, `scheduled`, `signal`; text + CHECK), `total` (integer, CHECK 0–100), `band` (`ScoreBand`; text + CHECK), `created_at`. Index `(workspace_id, idea_id, id DESC)` for history and latest.
3. `scoring.score_params`: `score_run_id` (FK, cascade), `workspace_id`, `param` (`ScoreParam`; text + CHECK), `raw` (integer, CHECK 0–10), `weighted` (numeric(5,2), CHECK 0–100), `reason` (text), `confidence` (numeric(3,2), CHECK 0–1), `no_evidence` (boolean), `evidence` (jsonb array of `{url, title, quote}`), `created_at`. Primary key `(score_run_id, param)`. A CHECK ties `no_evidence` to `evidence`: `no_evidence` is true exactly when `evidence` is an empty array.
4. The issue's column lists omit `workspace_id` on `score_params` and the `no_evidence` flag; `workspace_id` is added because every tenant row carries it and RLS policies key on it (architecture invariant), and `no_evidence` is the explicit flag the acceptance criteria ask for.
5. RLS through `enable_tenant_rls` on `score_runs` and `score_params`. The app role `metis_app` gets `SELECT` and `INSERT` only on both (no `UPDATE`, no `DELETE`): a score run cannot be changed even by a faulty query.

### Module (`server/metis/modules/scoring/`, layers as in `code-standards.md`)

6. Public surface (`__init__.py`): `router`, `ScoreParam`, `ScoreBand`, `ScoreTrigger`, `Rubric`, `NewParamScore`, `NewEvidence`, `ScoreRun`, `ScoreParamResult`, `ScoreDiff`, and the service functions below. Errors join `core/errors.py`.
7. Pure helpers (`helpers/`): `weighted_points(raw, weight)` = `raw / 10 * weight` (Decimal, 2 places); `total_from(params)` = sum of weighted points, rounded half up to an integer; `band_for(total)` = `build` at 75 and above, `promising` at 55–74, `advise` below 55. The band is taken from the rounded total.
8. Service functions (caller's session, never commit, scoped by workspace id as well as RLS, same rules as the ideas service):
   - `get_rubric(session)` → the latest `Rubric{version, weights}`.
   - `record_score(session, workspace_id, idea_id, run_id, params, trigger)` → `ScoreRun` (with its params). Steps, in one transaction: idea must exist and not be archived (else `IdeaNotFoundError`); the workflow run must exist and belong to that idea (else `RunNotFoundError`); validate `params` (9); load the latest rubric; compute each `weighted`, the `total` and the `band`; insert the run and its six params; add a `ScoreComputed` outbox event; set the idea's current score (10).
   - `latest_score(session, workspace_id, idea_id)` → newest `ScoreRun` with params, or `None`. Unknown/archived idea → `IdeaNotFoundError`.
   - `score_history(session, workspace_id, idea_id)` → `ScoreRunSummary` list (no params), newest first (uuid7 id order). Unknown/archived idea → `IdeaNotFoundError`.
   - `get_score_run(session, workspace_id, score_run_id)` → `ScoreRun` with params, or `ScoreRunNotFoundError` (also when the idea is archived).
   - `diff(session, workspace_id, a_id, b_id)` → `ScoreDiff{from_id, to_id, total_delta, band_changed, params: [{param, raw_delta, weighted_delta, confidence_delta}]}` where each delta is `b − a`, params in rubric order. Both runs must be of the same idea, else `InvalidInputError`; unknown → `ScoreRunNotFoundError`.
9. Validation of `params` (a list of `NewParamScore{param, raw, reason, confidence, evidence, no_evidence}`; text trimmed first through `helpers.validation.validate_input`):
   - exactly one entry for each of the six `ScoreParam` values; a missing, unknown or duplicate one → `InvalidInputError` (422) naming it;
   - `raw` is an integer 0–10; `confidence` 0–1 (2 decimals); `reason` 1–2,000 characters;
   - `evidence` holds at most 5 items `{url, title, quote}`: `url` an `http(s)` URL ≤ 2,048 characters, `title` 1–300, `quote` ≤ 2,000 (may be empty);
   - an empty `evidence` is accepted only with `no_evidence=true`; `no_evidence=true` with evidence, or empty evidence without the flag → `InvalidInputError`;
   - `no_evidence=true` caps `confidence` at `NO_EVIDENCE_MAX_CONFIDENCE` (0.30, named constant): a higher confidence is refused, not silently lowered.
10. Current score: `record_score` calls a new public function of the ideas module, `set_current_score(session, workspace_id, idea_id, score)`, that sets `ideas.current_score`. It does not bump the idea's `version` (so it never makes a user's edit stale) and does not change the stage. Not added by the issue; needed because `ideas.current_score` has no writer and the scoring module may not touch the `ideas` tables.
11. `ScoreComputed` event payload: `{idea_id, score_run_id, run_id, total, band, trigger, previous_total}` (`previous_total` is `null` for the first score). Written through `core.outbox.add_event` in the same transaction.
12. Immutability: no service function, repo function or DTO updates or deletes a score run or a param (items 5 and 8).

### Routes (`modules/scoring/controller/`, all on `current_workspace`, any member reads)

13. `GET /v1/ideas/{idea_id}/scores` → `{items: ScoreRunSummary[]}`, newest first, no pagination in MVP (a few scores per idea; weekly rescoring at most). `ScoreRunSummary`: `{id, idea_id, run_id, rubric_version, trigger, total, band, created_at}`. Unknown/archived/foreign idea → `404 idea.not_found`; no scores → `{items: []}`.
14. `GET /v1/ideas/{idea_id}/scores/latest` → `ScoreRunView`; no score yet → `404 score.not_found`; unknown/archived/foreign idea → `404 idea.not_found`.
15. `GET /v1/scores/{score_run_id}` → `ScoreRunView`; unknown/foreign/archived → `404 score.run_not_found`.
16. `ScoreRunView`: the summary fields plus `weights` (the rubric version's weights) and `params: [{param, weight, raw, weighted, reason, confidence, no_evidence, evidence: [{url, title, quote}]}]` in rubric order. `workspace_id` is never returned.
17. No write route: scores are written by the Scorer through the service. No route for `diff` in this PRD.

### Wiring and docs

18. Register the router in the API entrypoint. Import-linter: add `metis.modules.scoring` to the layers contract as a peer of `research` (`research | scoring`, both above `ideas`), so neither imports the other; add a contract "scoring uses only the public surface of ideas, identity and auth"; add `metis.modules.scoring` to the "auth imports no other domain module" list.
19. Errors added to `core/errors.py` (`score.not_found` 404, `score.run_not_found` 404; reuse `IdeaNotFoundError`, `RunNotFoundError`, `InvalidInputError`) and to the error table in `server-context.md`. Regenerate the web OpenAPI types (`npm run gen:api`) so the CI drift check passes.
20. Docs in the same change: `server-context.md` (Scoring module section, `ScoreParam`/`ScoreBand`/`ScoreTrigger` live in code, `ScoreComputed` payload, errors, ideas `set_current_score`), `architecture.md` (import rule now includes `scoring`).

## Out of scope

- The Scorer specialist, its tools (`get_rubric`, `submit_scores`), its prompt and Exa evidence gathering (SHIP-240).
- Suggestions (`SuggestionKind`) and their table, advice and the Advisor (later issues).
- Score calibration and rubric changes: only version 1 exists; no route or tool adds a rubric version.
- Writing the idea's stage after a score (the runner does; band-to-stage routing belongs to the Scorer/Advisor PRDs).
- A route for `diff`, a score-history chart or any web work (the score card UI is a later PRD).
- Idempotent scoring per workflow run: a Scorer node that re-runs after a crash will add another score run; SHIP-240 decides how it avoids that.
- Handlers for `ScoreComputed` (notifications, market watch).
- Pagination of the history.

## Touches

`server/metis/modules/scoring/*` (new), `server/metis/modules/ideas/` (public `set_current_score` only), `server/migrations/versions/0017_scoring.py`, `server/metis/core/errors.py`, `server/metis/entrypoints/api.py`, `server/pyproject.toml` (import-linter contracts), `server/tests/modules/scoring/*`, `web/lib/api/schema.d.ts` (generated), `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`.

## Testing Decisions

Good tests check behavior through the public surface (service functions, HTTP routes), against real Postgres with RLS on, as the ideas and research tests do. They do not reach into repos or SQL, except the migration test that checks grants and constraints.

Seams (highest available, all existing):

1. **Scoring service** (`metis.modules.scoring` functions on a real session) — most of the logic: weight math with known marks, band edges (a total of 54, 55, 74, 75 built from marks), rounding half up, missing / unknown / duplicate param refused, raw and confidence out of range, empty evidence needs the flag and caps confidence, idea archived or unknown refused, run of another idea refused, `ScoreComputed` in the outbox with `previous_total`, `ideas.current_score` follows the latest run, history order, `latest_score` is `None` with no scores, `diff` deltas. Prior art: `tests/modules/research/` service tests, `tests/modules/ideas/test_workflow_runs_service.py`.
2. **HTTP routes** (`httpx` against the app) — `ScoreRunView` shape and rubric order, `404`s (no score, unknown/archived/foreign idea, foreign score run), history order, no `workspace_id` in bodies. Prior art: `tests/modules/ideas/test_ideas_api.py`, `test_runs_api.py`; the route-auth walk in `tests/modules/auth/test_route_auth.py` covers the new routes automatically.
3. **Migration + RLS + immutability** — tables, CHECKs (raw, confidence, band, evidence flag), seeded rubric v1 summing to 100, RLS isolation across two workspaces as `metis_app`, and an `UPDATE`/`DELETE` on `score_runs` or `score_params` fails with a permission error as `metis_app`. Prior art: `tests/modules/ideas/test_interview_turns_migration.py`, the research migration test.
4. **Pure helpers** — a table test for `weighted_points`, `total_from` and `band_for` (no database).

## Dependencies

- `feat-ideas-crud` (SHIP-218) — done.
- Uses, all done: `feat-run-graph-job` (SHIP-228, `ideas.workflow_runs` for the `run_id` FK), `chore-outbox-relay` (SHIP-213, `add_event`).

## Acceptance criteria

- [x] Totals and bands match the rubric exactly (weights 25/25/15/15/10/10; edges 54 → `advise`, 55 → `promising`, 74 → `promising`, 75 → `build`).
- [x] Every param has a reason, a confidence and at least one evidence item, or the explicit `no_evidence` flag with confidence at most 0.30.
- [x] A submission without all six params is refused.
- [x] Score runs cannot be edited: no service path, and the app role cannot `UPDATE` or `DELETE` them.
- [x] `GET /v1/ideas/{id}/scores` returns the history newest first; `…/scores/latest` returns the newest with its params; `GET /v1/scores/{id}` returns one run.
- [x] `ideas.current_score` equals the latest score run's total after each `record_score`.
- [x] `ScoreComputed` is written in the same transaction as the score run.
- [x] RLS: workspace B cannot read workspace A's score runs or params (service and API).
- [x] `uv run ruff check`, `uv run mypy`, `uv run lint-imports` pass; web `npm run typecheck` passes after `gen:api`. `uv run pytest` runs in CI (not locally, per AGENTS.md); the 85 scoring tests passed locally before that rule.
- [x] `server-context.md` and `architecture.md` updated.

## Open questions

None.

## Resolved

1. **Layer position** (2026-11-20): `scoring` is a peer of `research` above `ideas`; neither imports the other.
2. **No evidence** (2026-11-20): empty `evidence` only with `no_evidence=true`; confidence above 0.30 is refused, not lowered.
3. **Current score** (2026-11-20): new public `ideas.set_current_score`, no `version` bump, no stage change.

## Decisions (from the issue and context files)

- `raw` is an integer 0–10 (no half marks); `weighted = raw / 10 * weight`, 2 decimals; `total` is the sum rounded half up; the band comes from the rounded total.
- The rubric version id is the version number (integer), not a uuid; the table is global.
- `run_id` is required: every score is made by a workflow run (manual, scheduled or signal rescores all go through the graph).
- History is unpaginated and ordered by uuid7 id, like interview turns and research items.

## Status

done
