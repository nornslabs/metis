# PRD: feat-scorer

Linear: SHIP-240 · https://linear.app/heimdallabs/issue/SHIP-240/24-scorer-specialist-with-evidence-backed-scores

Milestone: M4 — Scoring and advice. Branch: `feat/scorer`. Blocked by SHIP-238 (`feat-exa-researcher`, done) and SHIP-227 (`feat-scoring-module`, done). Blocks SHIP-241 (Advisor), SHIP-242 (manual rescore), SHIP-243 (scoring evals), SHIP-244 (Architect), SHIP-245 (web score card).

## Problem / Goal

Every run still goes through a stub Scorer: it moves the stage on and stores nothing. The `scoring` module (SHIP-227) can store immutable score runs and compute the total and band, and the Researcher (SHIP-238) leaves a closed snapshot of sourced competitors and market facts. Nothing joins them, so no idea ever gets a score, a band or a reason (project overview, success criterion 4).

Goal: replace the Scorer stub with a real tool-calling specialist. It reads the idea, the interview brief and the research snapshot, marks the six fixed parameters from 0 to 10 with a reason, evidence and confidence each (it may run up to 3 extra web searches to fill gaps), and submits them. The `scoring` module computes the total and band; the model never states a total. Then the run moves to `advising` (band `advise`) or `spec_draft`, and a `score` event tells the live run view.

## User stories

1. As a founder, I want my idea scored right after research, so that the plan rests on facts and a verdict.
2. As a founder, I want all six parameters marked, each with a reason, so that no mark is a bare number.
3. As a founder, I want evidence links and quotes behind each mark, so that I can check the claim myself.
4. As a founder, I want a confidence per parameter, so that I can tell a solid mark from a guess.
5. As a founder, I want a parameter with thin evidence to be marked conservatively with a low confidence, so that Metis never presents a guess as a fact.
6. As a founder, I want a parameter with no evidence to say so, so that a gap is visible.
7. As a founder, I want evidence that points only at sources Metis actually found (the research or the Scorer's own searches), so that no link is invented.
8. As a founder, I want the total and the band computed by Metis from the six marks, so that the total always agrees with the marks.
9. As a founder, I want an idea scoring below 55 to go to the Advisor, and 55 or more to go on to the spec, so that the next step fits the verdict.
10. As a founder, I want 54 to route to advising and 55 to spec drafting, so that the edge is predictable.
11. As a founder, I want to see the score appear in the live run, so that I do not have to reload.
12. As a founder, I want a run that was scored once not to score again when the Advisor sends it back, so that I do not get two verdicts from the same evidence.
13. As a founder, I want my idea still scored when I have no Exa key but research exists, so that a missing search key does not block a verdict.
14. As a founder, I want a clear failed run when the Scorer cannot produce a valid score, so that I know to retry, not a made-up score.
15. As a workspace member, I want scores hidden from other workspaces, so that my ideas stay private.
16. As a developer, I want the Scorer built on the shared ReAct builder with an allow-list (`web_search_exa`, `kb_lookup`, `get_rubric`, `submit_scores`), so that it can only do what it is allowed to.
17. As a developer, I want `submit_scores` to be the structured output (a finish tool), so that no code parses free text.
18. As a developer, I want the checks "all six parameters" and "evidence URLs are known sources" enforced in code, so that a model that ignores the prompt still cannot store an unsourced score.
19. As a developer, I want one refused submission to be fed back to the model once, so that a small slip does not fail the run.
20. As a developer, I want the Scorer's web searches capped at 3 per run in code, so that a looping model stops and the Researcher's 12-call cap is untouched.
21. As a developer, I want the weights read from the `scoring` module and only the written scale kept in the agent, so that there is one source of truth for weights.
22. As a developer, I want the Scorer to reach `scoring`, `research` and `ideas` only through their public surface, so that module boundaries hold.
23. As a developer, I want the new prompt as a new version file, so that runs stay traceable to the exact prompt text.
24. As a developer, I want the Advisor, Architect, Planner and Integrator to stay stubs, so that this change stays in one boundary.
25. As a developer, I want `AGENT_STUB_SPECIALISTS=true` to keep the stub Scorer, so that e2e and CI need no LLM key.

## Requirements

1. **Specialist** (`agent/specialists/scorer.py`): `build_scorer(gateway, open_session, redis, make_exa_client)` returns the Scorer node, wired in `runner._specialists` beside the Interviewer and Researcher. Purpose `score` (temperature 0.0), prompt `scorer.v2.md` (v1 exists and prompt versions are protected; the issue's `server/prompts/` path is stale), step limit 30, `finish_tools={submit_scores}`.
2. **Seed**: the idea, its `InterviewBrief`, the user's answers and the idea's latest closed research snapshot (summary, items with URL / quote / claim / confidence, competitors with URL, overlap, pricing). With no snapshot the seed says so; the model then needs its own searches or marks `no_evidence`.
3. **Tools** (allow-list, each in its own short committed transaction; no transaction is held while a model or Exa call runs):
   - `get_rubric()`: returns each parameter, its weight (from `scoring.get_rubric`) and the written scale (what 2, 5, 8 and 10 mean for it; see "Written scale"). The scale lives in the agent; the weights are never copied.
   - `kb_lookup(query, k?)`: the same read-only competitor lookup the Researcher has (reused, not copied).
   - `web_search_exa(query, …)`: the existing Exa search tool, search only (`exa_tools_for("scorer", …)`), capped at 3 calls per run by its own counter, separate from the Researcher's 12 (the 4th is not made and the model is told to submit).
   - `submit_scores(params[6])`: each `{param, raw, reason, confidence, evidence[{url, title, quote}], no_evidence}`; no total, no band. It checks (a) exactly one entry per parameter, (b) every evidence URL is a known source (below), then calls `scoring.record_score(trigger="manual")` and commits. A refusal returns a message to the model, not a failed run. The `scoring` module's own checks (integer `raw`, empty evidence only with `no_evidence=true` and confidence ≤ 0.30) are returned the same way.
4. **Known sources**: a URL is accepted when, compared after trimming and dropping a trailing `/` and a `#fragment`, it equals the URL of a snapshot item, a snapshot competitor, or a result of this run's `web_search_exa` calls (collected in memory by the Scorer's search wrapper; a crash re-run gets the same results from the Exa cache).
5. **Retry once**: the first refused submission is answered with what is wrong; the model may submit again. A second refused submission, or a loop that ends without a successful `submit_scores`, fails the run with `score.invalid_submission` (new error code, status 422, not retryable; see Open questions). A `GraphRecursionError` fails the run with `run.step_limit_reached`, as the Researcher does.
6. **Routing**: after a successful submission the node reads the run's score run back (`scoring.latest_score`) and sets the stage to `advising` when the band is `advise`, else `spec_draft`. Both are allowed transitions from `scoring`. The runner saves the stage; the node does not write `ideas.stage`.
7. **One score run per workflow run** (decides the open point in `feat-scoring-module`): on entry the node loads `scoring.latest_score`; when its `run_id` is this run, the node does not call the model. This covers the crash re-run and the pass after the Advisor, which today comes back to `scoring` once; there the stage goes to `spec_draft` (the stub Advisor's `ADVISED_MARKER` in `summary` says the Advisor has been; `advising` is chosen only when the marker is absent). SHIP-241 / SHIP-242 may change this when real rescoring arrives.
8. **Event**: new `RunEventType.SCORE` (`score`), a node-emitted type, payload `{score_run_id, total, band}`, published once right after a successful submission (not on the "already scored" path). Added to the SSE allow-list of node events (`NODE_EVENT_TYPES`). The web ignores unknown event names today and shows the score in SHIP-245.
9. **No Exa key**: the Scorer does not fail. It runs without `web_search_exa` and says so in its seed (see Open questions).
10. **`node_finished`** is emitted by the node (`scorer`) as the other real specialists do; `step_count` goes up by one.
11. **`ExaCallBudget`** gets an optional counter name (default unchanged: `agent:exa:{run_id}:calls`); the Scorer uses its own counter.
12. **Test wiring**: `job_ctx(…, llm=…)` keeps the Scorer a stub unless a test opts in, so the Interviewer and Researcher tests are not affected.

### Written scale (proposed, goes to `server-context.md`)

Marks are integers 0–10; 0–1 and 3–4, 6–7, 9 are between the anchors.

| Parameter (weight)     | 2                                         | 5                                              | 8                                                  | 10                                            |
| ---------------------- | ----------------------------------------- | ---------------------------------------------- | -------------------------------------------------- | --------------------------------------------- |
| `problem_severity` 25  | Nice to have; few people notice it        | Real, recurring annoyance; workarounds exist   | Costly or painful; people already pay or spend time | Urgent, frequent, expensive, hard to ignore   |
| `uniqueness` 25        | Many strong incumbents do the same        | Crowded, but a clear gap                       | Few, weak competitors and a clear difference       | No direct competitor and a defensible angle   |
| `market_demand` 15     | No sign of demand                         | Some signals; small market                     | Clear, growing demand; sizeable market             | Large, fast-growing, many paying customers    |
| `value` 15             | Marginal benefit                          | Clear but modest benefit                       | Large benefit; users would switch for it           | Transformative; obvious payback               |
| `feasibility` 10       | Needs tech, approval or capital not at hand | Doable by a small team with real risk        | Standard tech, small team, few unknowns            | Quick to build with proven tools              |
| `timing` 10            | Too early, or the market is shrinking     | Neutral                                        | A clear trend or enabler is arriving               | Strong tailwind now                           |

## Out of scope

- The Advisor, suggestions, rescoring, "Re-check market" and scheduled or signal triggers (SHIP-241, SHIP-242). `trigger` is always `manual` here, as the issue says.
- Scoring evals and calibration (SHIP-243).
- Web score card, history and the `score` event's UI (SHIP-245); no `web/` change.
- A new write route for scores, new tables or a migration (the module is done).
- Changing the rubric, weights or bands.
- Architect, Planner, Integrator.

## Touches

- `server/metis/agent/` — `specialists/scorer.py` (new), `tools/scoring.py` (new), `tools/exa.py` (named counter), `run_events.py` (allow `score`), `runner.py` (wire the real Scorer).
- `server/metis/core/events.py` (`RunEventType.SCORE`), `server/metis/core/errors.py` (`score.invalid_submission`).
- `server/metis/prompts/scorer.v2.md` (new).
- `server/tests/agent/` — `test_scorer.py` (new), `run_job_helpers.py` / `test_supervisor.py` as needed.
- `.agents/ctx/server-context.md`, `.agents/ctx/ui-context.md` (event table), `.agents/progress-tracker.md`.
- Reads `scoring`, `research`, `ideas`, `identity` through their `__init__.py` only; no new import layer.

## Dependencies

- `feat-exa-researcher` (SHIP-238): done.
- `feat-scoring-module` (SHIP-227): done.

## Testing

Seam: the `run_graph` job, called as Arq would, on real Postgres as `metis_app`, real Redis and the real checkpointer, with a scripted OpenAI-compatible LLM and the in-process `FakeExaMcp`, as in `tests/agent/test_researcher.py` (one seam; no new one). Tests check what the user and the database see: the stored score run, `ideas.current_score`, stage, events, run status, outbox. Tests run in CI, not locally.

- Valid submission: six params stored with reason, evidence and confidence; total and band computed by the module; `ideas.current_score` set; `score` event with total and band; `ScoreComputed` in the outbox; stage `spec_draft`.
- A model-stated total or band in the arguments is not accepted as a field (the schema has none).
- Missing parameter: refused once, corrected submission stored, one score run.
- Evidence URL not from the snapshot or a search: refused once, corrected submission stored; refused twice: run `failed` with `score.invalid_submission`, no score run.
- Evidence URL from a Scorer search is accepted; the 4th search is not made.
- Routing at the edges: marks totalling 54 → stage `advising`; 55 → `spec_draft`.
- Re-entry: a run that already has a score run makes no model call; after the stub Advisor the stage goes to `spec_draft` with one score run for the run.
- No snapshot: scores with `no_evidence` and confidence ≤ 0.30 are accepted.
- No Exa key: scored without a search tool; run `succeeded`.
- Step limit: `GraphRecursionError` fails the run with `run.step_limit_reached`.
- Unit: URL normalisation and the scale text (pure functions); `ExaCallBudget` named counters; supervisor routing unchanged.
- `uv run ruff check`, `uv run mypy`, `uv run lint-imports` pass locally; `uv run pytest` runs in CI.

## Acceptance criteria

- [x] Every stored score has all six parameters with reason, evidence (or `no_evidence`) and confidence.
- [x] The model never supplies a total or band; the `scoring` module computes both.
- [x] Every evidence URL is from the research snapshot or the Scorer's own searches.
- [x] Routing by band is correct at the edges (54 → `advising`, 55 → `spec_draft`).
- [x] The Scorer's web searches are capped at 3 per run; the Researcher's cap is unchanged.
- [x] A run records at most one score run, also after a crash re-run and after the Advisor stub.
- [x] A `score` event `{score_run_id, total, band}` is published after a successful submission.
- [x] `AGENT_STUB_SPECIALISTS=true` keeps the stub Scorer.
- [x] `ruff`, `mypy`, `lint-imports` pass; tests are added and run in CI.
- [x] `server-context.md` (Scorer, tools table, scale, event, error code), `ui-context.md` (event table) and the tracker are updated.

## Open questions

None open.

## Resolved

- Built: the shared `build_react_specialist` gained `refusals`, exception types a tool may raise to refuse a call; the model gets the message as an error result, which never ends the loop. A refused `submit_scores` could not be a plain string result, because a successful finish tool ends the loop. The second refusal returns "Submission is closed" as a success so the loop ends and the node fails the run.
- Built: `ExaCallBudget` takes a `counter` name (default `calls`); the Scorer uses `score_searches`. `kb_lookup_tool` in `research_kb.py` is public so the Scorer reuses the Researcher's lookup.
- Built: `job_ctx(…, llm=…)` keeps the Scorer a stub unless `score=True`.
- The `score` event is not yet known to the web (`parseRunEvent` returns `null`); SHIP-245 uses it.
- Built (code review): `submit_scores` validates its entries itself (the tool node would otherwise reject a malformed call before the tool runs, outside the refusal count); a key that is untested or failed its test also means no search tool, not a failed run; the seed lists competitor pricing.
- Built (CI fix): the step-limit error is caught inside the Exa session, because `open_mcp_session` turns any exception leaving its block into `UpstreamError` (it showed as `provider.upstream_error`). The Researcher has the same structure and was not changed.
- Tests are written but not run locally; CI runs them.

- A second refused (or missing) `submit_scores` fails the run with new `score.invalid_submission`; no score is stored (user, 2026-11-20).
- No Exa key: the Scorer runs without `web_search_exa` and scores from the snapshot, marking gaps `no_evidence` (user, 2026-11-20).
- Scorer entered again for a run that already has a score run: no model call, stage goes to `spec_draft`; SHIP-241 / SHIP-242 revisit it (user, 2026-11-20).

## Status

done
