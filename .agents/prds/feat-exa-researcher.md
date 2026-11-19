# PRD: feat-exa-researcher

Linear: SHIP-238 · https://linear.app/heimdallabs/issue/SHIP-238/21-researcher-specialist-and-interview-interleaving

Milestone: M3 — Interview and discovery. Branch: `feat/exa-researcher`. Blocked by SHIP-236 (Interviewer), SHIP-226 (Exa MCP tools), SHIP-229 (research module), all done. Blocks SHIP-239 (web interview chat and research panel), SHIP-240 (Scorer), SHIP-242 (rescore / re-check market).

## Problem / Goal

After the interview, every run still goes through a stub Researcher: it moves the stage to `scoring` and finds nothing. Metis promises real competitors and market facts with sources (project overview success criterion 3), and the Scorer (SHIP-240) needs that evidence. The pieces exist but are not joined: the `research` module stores snapshots, items and the competitor KB; `agent/tools/exa.py` gives run-scoped Exa MCP tools; the Interviewer leaves an `InterviewBrief` on the idea.

Goal: replace the Researcher stub with a real tool-calling specialist. It reads the brief, checks the workspace's competitor KB, searches Exa, fetches only promising pages, and saves sourced competitors and market facts into the run's research snapshot. When research raises a question only the user can answer, it may send up to 2 short questions back to the interview once per run, then continues. It closes the snapshot with a summary and moves the run to `scoring`.

## User stories

1. As a founder, I want Metis to research my idea right after the interview, so that the plan rests on facts, not only on my answers.
2. As a founder, I want real competitors with links, so that I can check them myself.
3. As a founder, I want each competitor's name, site, what it does, pricing when known and how much it overlaps with my idea, so that I can judge the threat.
4. As a founder, I want market facts (size, demand signals, trends, failures) with their source and the sentence that supports them, so that I can trust or reject each claim.
5. As a founder, I want each finding marked with a confidence, so that I know which ones are weak.
6. As a founder, I want an explicit "no direct competitors found" note when there are none, so that an empty list is not mistaken for a failure.
7. As a founder, I want a short research summary (top competitors, demand signals, risks), so that I get the picture without reading every item.
8. As a founder, I want Metis to ask me a short follow-up question when research finds something unclear, so that research goes the right way.
9. As a founder, I want at most one follow-up round of at most 2 questions, so that research does not turn into a second interview.
10. As a founder, I want follow-up questions to look and work like interview questions, so that I answer them in the same place.
11. As a founder, I want my follow-up answers kept if I reload or the worker restarts, so that I never answer twice.
12. As a founder, I want research to stay within a fixed number of web searches, so that a run does not burn my Exa credits.
13. As a founder, I want the run to move on to scoring once research is done, so that the pipeline keeps going.
14. As a founder, I want a clear failed run if my workspace has no Exa key, so that I know what to fix.
15. As a workspace member, I want competitors found for one idea to be reused for my other ideas, so that Metis does not search the same company twice.
16. As a workspace member, I want research hidden from other workspaces, so that my ideas stay private.
17. As a developer, I want the Researcher built on the shared ReAct builder with an allow-list (Exa search + fetch, KB lookup, KB upsert, save item, finish), so that it can only do what it is allowed to.
18. As a developer, I want the "no item without a URL" rule enforced in code (the research service), not only in the prompt, so that a model that ignores the prompt still cannot save an unsourced competitor or market fact.
19. As a developer, I want the Exa call cap enforced in code, so that a looping model still stops.
20. As a developer, I want the clarification round trip guarded by a counter in the graph state, so that research and interview can never loop.
21. As a developer, I want the research summary and clarification request produced as structured output (a finish tool), so that no code parses free text.
22. As a developer, I want the Researcher to reach the `research` and `ideas` modules only through their public surface, so that module boundaries hold.
23. As a developer, I want KB lookups and upserts to use embeddings when the workspace's model supports them and fall back to name/domain matching when not, so that research works on every OpenAI-compatible provider.
24. As a developer, I want the new prompt as a new version file, so that runs stay traceable to the exact prompt text.
25. As a developer, I want the Scorer, Advisor, Architect, Planner and Integrator to stay stubs, so that this change stays in one boundary.
26. As a developer, I want `AGENT_STUB_SPECIALISTS=true` to keep every specialist a stub, so that e2e runs need no LLM or Exa key.
27. As a developer, I want tests through the `run_graph` job with a scripted fake LLM and a fake Exa MCP server, so that the whole research flow is tested without real providers.
28. As an operator, I want every Exa call in the run's event stream as a `tool_call` event, so that the live run view shows research progress.

## Requirements

1. **KB and item tools** (`agent/tools/research_kb.py`). Bound to one run through a scope like `InterviewScope` (workspace, idea, run, session opener, gateway); each opens its own short, committed transaction. They call only `metis.modules.research` exports:
   - `kb_lookup(query, k?)`: embeds `query` through `LLMGateway.embed` (or `None` when embeddings are off) and calls `research.kb_lookup`; returns matches as JSON (name, url, domain, description, pricing, score, matched_by).
   - `kb_upsert_competitor(name, url, description?, pricing?, overlap)`: embeds name + description, calls `research.upsert_competitor`, then `research.link_competitor` on the run's snapshot with `overlap` (0–1). Returns the competitor's id and name.
   - `save_research_item(kind, title, url?, published_at?, quote?, claim, confidence)`: calls `research.add_item` on the run's snapshot. A `ResearchSourceMissingError` (or other validation error) becomes a message the model can act on, not a failed run.
   - `finish_research(summary, no_direct_competitors, needs_clarification)`: the structured output. `summary` is 1–4,000 characters (top competitors, demand signals, risks). `needs_clarification` is a list of 0–2 questions (each ≤ 500 characters).
2. **Snapshot lifecycle.** The Researcher calls `research.open_snapshot` at the start of every pass (returns the run's open snapshot if one exists, so a second pass after clarification and a crash-recovery re-run add to the same snapshot). It calls `research.close_snapshot(summary)` only when the run leaves research for `scoring`. When `no_direct_competitors` is true and the snapshot has no linked competitor, the summary must contain the sentence "No direct competitors found." (added by code if missing).
3. **Exa tools.** The Researcher gets `exa_tools_for("researcher", …)` from `load_exa_tools` (`web_search_exa`, `web_fetch_exa`). The issue's `exa_search` / `exa_get_contents` / `exa_find_similar` map to the two hosted MCP tools; there is no find-similar tool (see Resolved). The Exa MCP session is opened for the Researcher node only and closed when the node returns.
4. **Exa call cap.** At most 12 Exa calls per run (search + fetch, cached repeats included), enforced by a wrapper around the Exa tools: the 13th call does not reach Exa and returns a message telling the model to call `finish_research`. The count is a Redis counter per run (see Resolved), so the second pass and a crash re-run get only what is left.
5. **Prompt** `metis/prompts/researcher.v2.md` (v1 is protected and stays): work from the `InterviewBrief` (passed in the seed message with the idea's title and text); plan 3–6 queries (direct competitors, adjacent tools, market size / demand signals, recent news / trends, failures / shutdowns); `kb_lookup` before searching for a competitor; fetch only promising hits; record each competitor with name, URL, what it does, pricing if found and overlap; never save an item without a URL; quote the supporting sentence; mark confidence; ask for clarification only when an answer would change the research and only the user knows it; finish once coverage is met or the cap is reached. Untrusted-data rule kept.
6. **Interleaving.**
   - New `MetisState` fields: `clarification: list[str] | None` (the Researcher's pending questions), `clarification_rounds: int` (0 or 1). Read with defaults so checkpoints written before this change still load.
   - When `finish_research` returns questions and `clarification_rounds == 0`, the Researcher node sets `clarification` and `clarification_rounds = 1`, leaves the stage `researching` and does not close the snapshot. With `clarification_rounds == 1` the questions are ignored (logged) and research finishes.
   - The supervisor routes to the Interviewer whenever `clarification` is set, whatever the stage. `STAGE_ROUTES` is unchanged; the supervisor stays pure.
   - The Interviewer, when `clarification` is set, asks each question through the same interview path as `ask_user` (saved turn with topic `other`, `interrupt({"type": "question", "question"})`, answer saved after resume), with no model call, then clears `clarification`. The supervisor then routes back to the Researcher by stage.
   - The second Researcher pass is seeded with the brief, the clarification questions and answers, and what the open snapshot already holds.
7. **Specialist** (`agent/specialists/researcher.py`): `build_react_specialist` over the v2 prompt, the tools above and the run's `research` chat model, with `finish_tools={finish_research}`. On finish: clarification (item 6) or close the snapshot and return `stage: scoring`. Emits `node_finished`; `step_count` +1 per node visit. Hitting the step limit ends the run with `run.step_limit_reached`, like the Interviewer. It never writes `ideas.stage`.
8. **Runner wiring.** `_specialists` adds the real Researcher next to the real Interviewer unless `AGENT_STUB_SPECIALISTS` is true. The Researcher needs Redis (Exa cache and `tool_call` events) and an HTTP client factory for Exa; `RunnerDeps` gains an `exa_http_client` factory so tests point Exa at the fake. No Exa key → `ProviderNotConfiguredError` → run `failed` with `provider.not_configured`. Exa failures keep the `provider.upstream_error` mapping from SHIP-226.
9. **Docs.** `server-context.md` (Researcher behaviour, tools and payloads, state fields, supervisor clarification route, Interviewer clarification mode, Exa cap, prompt v2), `architecture.md` if the run flow description changes, tracker. Notion LLD sync follows.

## Out of scope

- Scheduled market watch and `signals` (issue Out of scope).
- Real Scorer, Advisor, Architect, Planner, Integrator.
- Any web UI change (the research panel is SHIP-239; the question card already renders `interrupt` events).
- New research HTTP routes (SHIP-229 already serves the snapshot).
- A find-similar Exa tool or any non-Exa research source.
- Writing `ideas.stage` (stage sync stays a separate issue).
- USD budget enforcement (SHIP-237).
- Re-check market / rescore (SHIP-242).

## Touches

`server/metis/agent/specialists/researcher.py` (new), `server/metis/agent/tools/research_kb.py` (new), `server/metis/agent/specialists/interviewer.py` (clarification mode), `server/metis/agent/supervisor.py` (clarification route), `server/metis/agent/state.py` (new fields), `server/metis/agent/runner.py` (wiring, `exa_http_client`), `server/metis/agent/tools/exa.py` (only if the call-cap wrapper belongs there), `server/metis/prompts/researcher.v2.md` (new), `server/tests/agent/`, `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`, `.agents/progress-tracker.md`.

## Testing Decisions

- **What a good test does:** drives the run from the outside and asserts what the user, the database and the event stream see: questions asked, `tool_call` events, run status, the closed snapshot with its items, linked competitors and summary, KB rows, the final stage. It does not assert prompts, message lists or tool internals.
- **Seam (one, the highest):** the `run_graph` job (`execute_run`) on real Postgres as `metis_app` and real Redis, with the LLM faked at the HTTP boundary by `FakeLLMServer` (scripted chat completions with tool calls, embeddings) and Exa faked by `FakeExaMcp` through the new `exa_http_client` factory. Resume is a second `execute_run` with `resume=<answer>`. The Interviewer is scripted to finish at once (or a stored brief is used) so tests start at research. Prior art: `tests/agent/test_interviewer.py`, `interview_helpers.py`, `llm_helpers.py`, `run_job_helpers.py`, `test_exa_tools.py` (`FakeExaMcp`).
- Tests planned at that seam:
  - Happy path: search → fetch → `kb_upsert_competitor` → `save_research_item` (market fact) → `finish_research` → snapshot closed with summary, competitor linked with overlap, items have URLs and quotes, stage → `scoring`, stubs carry the run to `succeeded`, one `tool_call` event per Exa call.
  - No URL: `save_research_item(kind=competitor)` without URL → model gets a message, nothing saved, run continues.
  - No competitors: `finish_research(no_direct_competitors=true)` → summary contains "No direct competitors found."
  - KB dedupe: a competitor already in the workspace KB is found by `kb_lookup`; upserting the same domain keeps one KB row and links it.
  - Embeddings off: the fake LLM rejects embeddings → lookups fall back to name/domain; research still finishes.
  - Clarification: `finish_research` with 2 questions → run `awaiting_user` with the first question; answers → second; Researcher runs again on the same snapshot and finishes; turns saved with topic `other`.
  - At most once: the second pass asks for clarification again → ignored, snapshot closed, stage `scoring`; only 2 clarification turns exist.
  - Cap: a model that keeps searching → Exa receives at most 12 calls across both passes; the model is told to finish.
  - Re-run safety: resume and crash recovery reuse the open snapshot and do not duplicate clarification turns.
  - No Exa key → run `failed` with `provider.not_configured`.
  - Stub setting: `AGENT_STUB_SPECIALISTS=true` still runs to `succeeded` with no keys.
- **Unit:** `test_supervisor.py` gains the clarification route (pure function).
- `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run lint-imports` pass.

## Dependencies

- `feat-interviewer` (SHIP-236): done.
- `feat-exa-mcp-tools` (SHIP-226): built and merged (`agent/tools/exa.py`); its PRD has no Status line.
- `feat-research-module` (SHIP-229): done.

## Acceptance criteria

- [x] A run produces a closed snapshot with at least one competitor or an explicit "No direct competitors found." note; every competitor and market fact has a source link.
- [x] At most one clarification round trip (≤ 2 questions) per run.
- [x] The Exa call cap (12 per run) is respected.
- [x] Stage moves to `scoring` after research; `ideas.stage` is not written.
- [x] Tests above pass; `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run lint-imports` pass.
- [x] `server-context.md`, `architecture.md` (if changed) and the tracker are updated.

## Open questions

None open.

## Resolved

- Built: `open_exa_tools(api_key, …)` split out of `load_exa_tools` so the Researcher reads the Exa key in its own short transaction and holds no database session while Exa runs; `ExaCallBudget` / `with_call_cap` live in `agent/tools/exa.py`. `finished_call_args` (shared by both specialists) lives in `specialists/base.py`.
- Built (code review): the Exa cap is a Redis counter (`agent:exa:{run_id}:calls`), not a state field, so a crash re-run cannot spend it again; `research_tool_calls` was dropped. A node re-run after the snapshot closed only moves the run to `scoring`. `save_research_item` also refuses a `competitor`/`market_fact` without a quote. `kb_upsert_competitor` no longer reports `already_in_kb` (it was guessed from timestamps). A linked competitor's own URL is its only source link; its evidence is the sourced items.
- Built: clarification questions are asked one per Interviewer visit (the rest stay in state), which keeps one pause per node run.
- Built: when the snapshot has no linked competitor, "No direct competitors found." is always added to the summary (not only when the model sets `no_direct_competitors`).
- Tests: `tests/agent/test_researcher.py` (11, at the `run_graph` job seam with a scripted LLM and `FakeExaMcp`), a routing test in `test_supervisor.py`; `ScriptedLLM` now answers embeddings (404 by default) and `job_ctx` keeps the Researcher a stub unless an Exa client is given.

- Clarification routing: state fields `clarification` + `clarification_rounds`; the stage stays `researching`; the supervisor routes to the Interviewer while `clarification` is set; the Interviewer asks the questions verbatim with no model call (user, 2026-11-19).
- Clarification questions go through `ideas.open_question` (topic `other`), count toward the 8-question cap and honour "That's enough"; a refused question is skipped and research continues (user, 2026-11-19).
- The 12-call cap counts Exa calls only (search + fetch), per run across both passes (user, 2026-11-19).
- No Exa key fails the run with `provider.not_configured` (user, 2026-11-19).
- PRD path: the issue's Agent notes say `.agents/PRDs/feat-exa-researcher.md`; the folder is `.agents/prds/`.
- Exa tool names: the hosted MCP server gives `web_search_exa` and `web_fetch_exa` (decision 2026-11-14, SHIP-226); `exa_search` → `web_search_exa`, `exa_get_contents` → `web_fetch_exa`, no find-similar.
- Prompt goes in `metis/prompts/researcher.v2.md`: v1 exists and prompt versions are protected; the issue's `server/prompts/` path is stale.
- Structured output is a `finish_research` tool call (same pattern as `finish_interview`), not a new port method.
- The URL rule is already enforced by `research.add_item` (`ResearchSourceMissingError`) and the `ck_items_source_url` CHECK.

## Status

done
