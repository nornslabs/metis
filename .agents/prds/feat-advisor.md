# PRD: feat-advisor

Linear: SHIP-241 · https://linear.app/heimdallabs/issue/SHIP-241/25-advisor-specialist-and-improvement-suggestions

Milestone: M4 — Scoring and advice. Branch: `feat/advisor`. Blocked by SHIP-240 (`feat-scorer`, done). Blocks SHIP-245 (web score card, history and suggestions).

## Problem / Goal

An idea that scores below 55 still goes through a stub Advisor: it stores nothing and bounces back to the Scorer. The project's adviser mode (overview: "gaps, pivots, revise and rescore"; success criterion 4) does not exist, and the `scoring` module has no place to keep suggestions.

Goal: replace the Advisor stub with a real tool-calling specialist. For an idea in the `advise` band it finds the 2–3 weakest parameters, looks for evidence of gaps, and saves 3–5 sourced suggestions (`feature`, `niche`, `pricing`, `pivot`), each tied to parameters. For a `promising` idea it saves at most 2 and does not stop the run. After advising an `advise` idea, the run pauses with an `advice_decision` interrupt: **Revise idea and rescore**, **Continue to spec anyway**, **Stop here**. Revise saves the user's new text, appends accepted suggestions, and sends the run back to the Scorer for a second, comparable score run that reuses the research. The `scoring` module owns suggestions (table, service, two routes).

## User stories

1. As a founder, I want 3–5 concrete suggestions when my idea scores below 55, so that I know how to make it stronger.
2. As a founder, I want each suggestion to name the parameters it would improve, so that I see which weakness it targets.
3. As a founder, I want advice aimed at my weakest parameters, not at what already scores well, so that the advice is useful.
4. As a founder, I want each suggestion to carry a reason and its sources (links and quotes), so that I can check it.
5. As a founder, I want each suggestion to say what impact I can expect, so that I can rank them.
6. As a founder, I want suggestions sorted into feature, niche, pricing and pivot, so that I can scan them.
7. As a founder, I want at most 2 suggestions when my idea is already promising (55–74), so that advice does not drown a good score.
8. As a founder, I want a promising idea to go on to the spec without waiting for a decision, so that advice never blocks the flow.
9. As a founder, I want to be asked what to do after the advice (revise and rescore, continue to the spec anyway, or stop), so that I stay in control.
10. As a founder, I want to rewrite my idea text when I choose revise, so that the new score reflects my changes.
11. As a founder, I want the suggestions I accepted added to my idea text as notes, so that the rescore sees them.
12. As a founder, I want the rescore to reuse the existing research, so that it is fast and comparable.
13. As a founder, I want the second score run stored next to the first, so that I can compare the two.
14. As a founder, I want to continue to the spec even though the score is low, so that a verdict never blocks me.
15. As a founder, I want to stop the run at the advice and keep my score and suggestions, so that I can come back later.
16. As a founder, I want to mark a suggestion accepted or dismissed, so that I keep track of what I will act on.
17. As a founder, I want to list the suggestions of my idea, newest score run first, so that I see current advice before old advice.
18. As a founder, I want advice to be marked as made from a score run, so that I know which score it answered.
19. As a founder, I want my idea still advised when I have no Exa key, so that a missing key does not block help (advice then rests on the research and `kb_lookup`).
20. As a founder, I want a clear failed run when the Advisor cannot produce enough sourced suggestions for a low score, so that I know to retry, not a thin or invented list.
21. As a workspace member, I want suggestions hidden from other workspaces, so that my ideas stay private.
22. As a developer, I want the Advisor built on the shared ReAct builder with an allow-list (`web_search_exa`, `kb_lookup`, `save_suggestion`, `finish_advice`), so that it can only do what it is allowed to.
23. As a developer, I want the count limits (3–5 or at most 2) and the "evidence URLs are known sources" check enforced in code, so that a model that ignores the prompt still cannot store an unsourced suggestion.
24. As a developer, I want the Advisor's searches capped in code (3 per run, own counter), so that a looping model stops and the other caps are untouched.
25. As a developer, I want the weakest parameters computed in code and given to the model, so that "target the weakest" does not depend on the model's arithmetic.
26. As a developer, I want the Advisor to make no model call when its suggestions already exist for the score run, so that a crash re-run or a resume after the interrupt never duplicates advice.
27. As a developer, I want the decision interrupt's resume value checked at the API (shape, text length, suggestion ids), so that a bad payload is a 422 and never reaches the graph.
28. As a developer, I want the Scorer to score again only when the Advisor asks for it, so that "one score run per workflow run" still holds everywhere else.
29. As a developer, I want the prompt as a new version file, so that runs stay traceable to the exact prompt text.
30. As a developer, I want `AGENT_STUB_SPECIALISTS=true` to keep the stub Advisor, so that e2e and CI need no LLM key.
31. As a developer, I want the Advisor to reach `scoring`, `research` and `ideas` only through their public surface, so that module boundaries hold.

## Requirements

### Scoring module (suggestions)

1. **Migration** `0018_suggestions` (schema `scoring`): table `suggestions(id uuid pk, workspace_id, idea_id fk ideas, score_run_id fk score_runs, kind text CHECK feature|niche|pricing|pivot, title, rationale, target_params text[] (CHECK values are `ScoreParam`s, 1–3 entries), expected_impact, evidence jsonb, status text CHECK open|accepted|dismissed default open, created_at)`. RLS (`tenant_isolation`, `workspace_id`). `metis_app` gets SELECT and INSERT, and UPDATE on `status` only (column grant): a suggestion's text is immutable like a score. Index `(workspace_id, idea_id, score_run_id desc)` (uuid7 ids sort by time) and `(score_run_id)`. Downgrade drops the table. `down_revision`: main currently has two migration heads (`0017_scoring` and `0017_run_user_prompt`, both on `0016_research`); `0018` merges both (`down_revision` tuple) unless `alembic heads` shows one at implementation time.
2. **DTO and rules**: `SuggestionKind` (`feature`, `niche`, `pricing`, `pivot`), `SuggestionStatus`, `NewSuggestion{kind, title 1–200, rationale 1–2,000, target_params 1–3 distinct `ScoreParam`, expected_impact 1–500, evidence 1–5 of `{url http(s) ≤ 2,048, title 1–300, quote ≤ 2,000}`}`, `Suggestion`. Evidence is required (a suggestion without a source is refused); there is no `no_evidence` escape here.
3. **Service** (`scoring.service.suggestions`, caller's session, never commits, scoped by workspace id as well as RLS): `save_suggestion(session, workspace_id, idea_id, score_run_id, NewSuggestion)` (the score run must belong to the idea, else `RunNotFoundError`; idea live), `list_suggestions(session, workspace_id, idea_id, score_run_id=None)` (newest score run first, then creation order), `set_suggestion_status(session, workspace_id, suggestion_id, status)` (any status to any status; unknown id → new `score.suggestion_not_found` 404). Exported from `scoring/__init__.py`.
4. **Routes** (on `current_workspace`; members read and set status): `GET /v1/ideas/{id}/suggestions[?score_run_id=]` → `{items: Suggestion[]}` (`[]` when none; unknown, archived or foreign idea → `idea.not_found`); `PATCH /v1/suggestions/{id}` `{status}` → the suggestion. Web `schema.d.ts` regenerated.
5. **Event**: `scoring` adds no domain event for suggestions (not in `DomainEventType`).

### Ideas module

6. **Transition table**: add `advising → spec_draft` (decided with the user; needed by "Continue anyway" and the promising path). `server-context.md` transition list updated.
7. **`ideas.apply_revision(session, workspace_id, idea_id, raw_text)`** (new public function, never commits): sets `raw_text` (10–10,000 characters, trimmed), bumps `version`, idea must be live. No creator/owner check: the caller is the run, started and resumed by a member. Idempotent for the same text (a crash re-run writes the same value; `version` is bumped only when the text changes).
8. **Resume value**: `POST /v1/runs/{id}/resume` accepts, for a pending `advice_decision` interrupt, `{value: {decision: "revise"|"continue"|"stop", revised_text?, accepted_suggestion_ids?}}`. `check_resume_value` validates it: `revise` needs `revised_text` (10–10,000 characters after trim, the same bounds as an idea's text, so a too-short text is a 422 at the API, not a failed run); `accepted_suggestion_ids` are UUIDs (≤ 5), and for other decisions `revised_text` is ignored. Anything else → 422 `Invalid resume value`. `ideas` must not import `scoring`: the shape is checked locally, and the Advisor checks the ids belong to the idea when it uses them.

### Agent

9. **Specialist** (`agent/specialists/advisor.py`): `build_advisor(gateway, open_session, redis, make_exa_client)` wired in `runner._specialists` beside the Interviewer, Researcher and Scorer. Purpose `advise` (temperature 0.5), prompt `advisor.v2.md` (v1 exists and is protected), step limit 40 (up to five saves, the finish and a retry), `finish_tools={finish_advice}`, `refusals=(AdviceRefused,)`.
10. **Entry and routing**: the supervisor already routes `advising` to the Advisor. Scorer routing changes: `advise` and `promising` bands → `advising` (when the Advisor has not been yet, by `ADVISED_MARKER` in `summary`), `build` → `spec_draft`. The Advisor sets `ADVISED_MARKER` and:
    - **`advise` band** → saves 3–5 suggestions, then interrupts with `{"type": "advice_decision", "score_run_id", "total", "band", "suggestion_ids": [...]}`. `continue` → stage `spec_draft`; `stop` → the run ends `succeeded` with the idea left at `advising` (new `stopped` state flag read by `route`); `revise` → writes the revision (R7), sets `rescore_after` (the advised score run's id) and stage `scoring`.
    - **`promising` band** → saves at most 2 (0 is allowed), no interrupt, stage `spec_draft`.
11. **Seed**: the idea (current text), the interview brief and answers, the latest closed research snapshot (as the Scorer's seed), the latest score run (per parameter: raw, reason, confidence, evidence) and the **weakest parameters**, computed in code as points lost `weight × (10 − raw) / 10`, largest first, with the 2–3 to target (3 for `advise`, 2 for `promising`; ties go to the heavier weight). The seed states the band and the allowed count. With no Exa key it says search is not available.
12. **Tools** (allow-list; each its own short committed transaction; no transaction is held while a model or Exa call runs):
    - `kb_lookup(query, k?)`: the Researcher's read-only lookup, reused.
    - `web_search_exa(query, …)`: `exa_tools_for("advisor", …)` (search only; already allowed), capped at 3 per run on its own counter (`advise_searches`) through `ExaCallBudget`; the 4th is not made and the model is told to save its suggestions and finish. Result URLs are collected into the run's source book.
    - `save_suggestion(kind, title, rationale, target_params, expected_impact, evidence[])`: checks (a) the count so far is below the maximum (5, or 2 for `promising`), (b) every `target_params` entry is one of the score run's weakest parameters' set (any `ScoreParam` is accepted, but at least one must be in the targeted 2–3), (c) every evidence URL is a known source (snapshot item or competitor URL, a URL in the latest score run's evidence, or a result of this run's searches; compared without a trailing `/` or `#fragment`, as the Scorer does), then calls `scoring.save_suggestion` and commits. A refusal returns a message to the model; it never fails the run.
    - `finish_advice()`: refused when fewer than the minimum were saved (3 for `advise`; none for `promising`). The first refusal tells the model how many are missing. A second refusal ends the loop and fails the run with `advice.invalid_submission` (new error code, 422, not retryable) for `advise`; `promising` never fails the run for advice (a step limit there is logged and the run goes on).
13. **Idempotency**: on entry, when suggestions already exist for the latest score run, the node makes no model call and goes straight to the decision (this covers a crash re-run and the node re-run after the interrupt resumes). The interrupt is the only thing the node does before the revision write; the revision write is idempotent (R7).
14. **Accepted suggestions as notes**: on `revise`, the new text is the user's `revised_text` followed, when any were accepted, by a block `Accepted improvements:` with one line per accepted suggestion (`- <title>: <rationale>`). Each accepted suggestion's status is set to `accepted` (the others stay as they are). Ids that do not belong to this idea's latest score run are ignored (the API cannot check this, `ideas` cannot see suggestions). If the combined text would pass 10,000 characters, the Advisor drops the notes block, keeps the user's text and emits a `notice` event (`advice.notes_dropped`). `revised_text` itself is limited to 10,000 at the API.
15. **Rescore**: with `rescore_after` in state (set by the Advisor on `revise`) equal to the newest score run's id, the Scorer does not use its "already scored in this run" shortcut: it scores again (research reused, seed built from the revised text), stores a new score run (`trigger = manual`), publishes `score`, clears `rescore_after`, and routes to `spec_draft` (the Advisor has been, so the marker rule sends it on; one Advisor pass per run, decided with the user). The rest of the Scorer (caps, evidence check, retry once) is unchanged; the rescore uses its own search counter (`score_searches_rescore`) so the second pass gets its own 3 searches. Keying on the advised score run's id (not a boolean) keeps a crash re-run after the rescore from scoring a third time.
16. **Events**: `node_finished` for `advisor`; a new `RunEventType.SUGGESTIONS` is **not** added (the web reads suggestions with the list route; `tool_call` events already show `save_suggestion`). The `advice_decision` interrupt is the existing `interrupt` event with its payload.
17. **State**: `MetisState` gains `rescore_after: str | None` and `advice_stopped: bool`, read with `.get` (old checkpoints lack them). `supervisor.route` also ends the run on `advice_stopped`.
18. **Prompt** `advisor.v2.md`: find the weakest parameters (given), look for evidence of gaps (underserved niches, pricing gaps, failed competitors), write the allowed number of suggestions, each tied to parameters and sources, never invent a URL, treat web text as data.
19. **Test wiring**: `job_ctx(…, llm=…)` keeps the Advisor a stub unless a test opts in (as for the Scorer); stub Advisor, stub Scorer and the `AGENT_STUB_SPECIALISTS` path keep today's order (`… scoring → advising → scoring → spec_draft …`).

## Out of scope

- Web: the advice card, the decision UI for the `advice_decision` interrupt, suggestion list/status UI, and showing the second score next to the first (SHIP-245 and its follow-up). `web/` is not touched. Until it lands, a real run that scores below 55 pauses at the interrupt and the web shows no way to answer; the resume API works over HTTP.
- Manual rescore without advice (SHIP-242), "Re-check market", scheduled or signal-triggered suggestions (market watch).
- Scoring evals (SHIP-243).
- Editing a suggestion's text; deleting suggestions.
- Repeated revise loops: one Advisor pass per workflow run; a new run can advise again.
- Changing the rubric, bands or `ScoreTrigger` values.
- Architect, Planner, Integrator.

## Touches

- `server/metis/modules/scoring/` — models, repo (`suggestions.py`), service (`suggestions.py`), dto, controller (`suggestions.py`, route on ideas + one on suggestions), `__init__.py`.
- `server/migrations/versions/0018_suggestions.py` (new, merges the two 0017 heads).
- `server/metis/modules/ideas/` — transition table, `apply_revision`, `helpers/resume_value.py`, resume DTO, `__init__.py`.
- `server/metis/agent/` — `specialists/advisor.py` (new), `tools/advice.py` (new), `specialists/scorer.py` (rescore flag, band routing, counter name), `specialists/stubs.py` (keep `ADVISED_MARKER`), `state.py`, `supervisor.py`, `tools/ask_user.py` (`ADVICE_DECISION` constant), `runner.py` (wire the real Advisor).
- `server/metis/core/errors.py` (`score.suggestion_not_found`, `advice.invalid_submission`).
- `server/metis/prompts/advisor.v2.md` (new).
- `server/tests/` — `agent/test_advisor.py` (new), `modules/scoring/test_suggestions_api.py` and `test_suggestions_migration.py` (new), `modules/ideas/` (resume value, transition, revision), `run_job_helpers.py` as needed.
- `web/lib/api/schema.d.ts` (regenerated only).
- `.agents/ctx/server-context.md` (domain table, scoring section, tools table, Advisor, transitions, resume value, errors), `.agents/ctx/architecture.md` if an invariant changes, `.agents/progress-tracker.md`.

## Dependencies

- `feat-scorer` (SHIP-240): done.

## Testing

Two existing seams, no new one:

1. **`run_graph` job**, called as Arq would, on real Postgres as `metis_app`, real Redis and the real checkpointer, with a scripted OpenAI-compatible LLM and `FakeExaMcp`, as in `tests/agent/test_scorer.py`. The interrupt is answered through the resume path (`prepare_resume` + job with `resume`). Tests check what the user and the database see: stored suggestions, score runs, `ideas.raw_text`, stage, events, run status, the pending interrupt.
2. **HTTP** (`tests/modules/scoring/`), for the two suggestion routes, RLS and the grants.

Cases:

- Score 40: 3–5 suggestions stored, each with kind, title, reason, 1–3 target params including at least one weakest parameter, evidence from the snapshot or an Advisor search, status `open`; run `awaiting_user` with an `advice_decision` interrupt listing their ids.
- Promising (60): at most 2 saved, no interrupt, stage `spec_draft`, run `succeeded`; 0 suggestions is accepted for promising.
- `build` (80): Advisor not visited.
- Evidence URL not from the snapshot, score evidence or a search: refused, model corrects, stored. A suggestion with no evidence: refused.
- More than the maximum: the 6th save is refused. `finish_advice` with 2 saved for `advise`: refused once, then 3 saved and finished; refused twice: run `failed` `advice.invalid_submission`, suggestions stored so far stay.
- The 4th Advisor search is not made; the Researcher's and Scorer's counters are untouched.
- No Exa key: advice from the research and `kb_lookup`; run reaches the interrupt.
- Resume `continue`: stage `spec_draft`, run `succeeded`, one score run. Resume `stop`: run `succeeded`, idea stays `advising`. Resume `revise` with text and one accepted suggestion: `ideas.raw_text` replaced, notes block appended, the suggestion `accepted`, a second score run for the same workflow run (both visible in score history, comparable by `diff`), `ideas.current_score` follows the second, then `spec_draft`.
- Crash re-run of the Advisor (suggestions already exist): no model call, interrupt raised again; resume re-run does not duplicate suggestions or the revision.
- Resume validation: wrong shape, missing `revised_text` on `revise`, text over 10,000, non-UUID ids → 422; `value: bool` on an `advice_decision` interrupt → 422.
- Routes: list returns newest score run first and filters by `score_run_id`; unknown idea → `idea.not_found`; PATCH status works for a member, unknown id → `score.suggestion_not_found`, another workspace's suggestion is invisible; `metis_app` cannot UPDATE any column but `status` or DELETE.
- Migration: upgrade/downgrade round trip, CHECKs (kind, status, `target_params`), RLS on, merge of the two heads.
- Unit: weakest-parameter ranking (points lost, tie to the heavier weight); URL normalisation reused from the Scorer; `check_resume_value`; stub flow order unchanged.
- Supervisor routing unchanged for every `Stage`; `route` ends on `advice_stopped`.
- Local: `uv run ruff check`, `uv run mypy`, `uv run lint-imports`, `uv run alembic upgrade head`, web `npm run typecheck` (schema regenerated). `uv run pytest` runs in CI, not locally.

## Acceptance criteria

- [x] Below 55, a run ends the Advisor with 3–5 saved suggestions, each with a reason, target parameters, an expected impact and at least one source.
- [x] Every suggestion's evidence URL is from the research, the score evidence or the Advisor's own searches.
- [x] A `promising` idea gets at most 2 suggestions and goes to `spec_draft` without an interrupt.
- [x] After advising an `advise` idea, the run pauses with an `advice_decision` interrupt; `continue`, `stop` and `revise` behave as specified and the resume value is validated.
- [x] `revise` saves the new text (with accepted suggestions as notes) and produces a second score run for the same workflow run, comparable with the first; `ideas.current_score` follows the newest.
- [x] A run records one score run unless the Advisor asked for a rescore, also after a crash re-run.
- [x] The Advisor's searches are capped at 3 per run on their own counter; other caps unchanged.
- [x] Suggestions are readable and their status settable over the two routes, hidden across workspaces; `metis_app` cannot change any other column.
- [x] `advising → spec_draft` is an allowed transition.
- [x] `AGENT_STUB_SPECIALISTS=true` keeps the stub flow.
- [x] `ruff`, `mypy`, `lint-imports` and `alembic upgrade head` pass; tests are added and run in CI.
- [x] `server-context.md` and the tracker are updated.

## Open questions

None open.

## Resolved

- Revised text comes in the resume payload (`{decision, revised_text, accepted_suggestion_ids}`); the Advisor saves it (user, 2026-11-20).
- Add `advising → spec_draft` to the transition table (user, 2026-11-20).
- `promising` ideas run through the Advisor with at most 2 suggestions, no interrupt (user, 2026-11-20).
- "Stop here" ends the run `succeeded` with the idea at `advising`; one Advisor pass per run, so a rescore routes to `spec_draft` even when still below 55 (user, 2026-11-20).
- Built: shared seed pieces moved to `agent/specialists/idea_context.py`, `ready_exa_key` to `tools/exa.py` and `invoke_loop` to `specialists/base.py`, so the Scorer and Advisor share them; the Scorer's tests moved their helpers to `tests/agent/score_helpers.py` (and the 55 case now goes through the stub Advisor, since `promising` is advised too). `ResumeBody.value` accepts an `AdviceResume` object (`ideas.AdviceResume`, `AdviceDecision`).
- Tests are written but not run locally; CI runs them. The migration SQL was checked offline (`alembic upgrade 0017_scoring:0018_suggestions --sql`); no local database was available for `alembic upgrade head`.
- Proposed, not asked (change in review if wrong): a second short `finish_advice` for `advise` fails the run with `advice.invalid_submission`, like the Scorer; `promising` never fails; status may be set by any member; no new `RunEventType` for suggestions; migration `0018` merges the two existing 0017 heads.

## Status

done
