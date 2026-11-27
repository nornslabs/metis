# PRD: feat-researcher-gate

Linear: SHIP-417 · https://linear.app/heimdallabs/issue/SHIP-417/researcher-gate

Parent: SHIP-414. Branch: `feat/researcher-gate` (stacked on `feat/interviewer-gates` until its PR is merged; both stack on `feat/soul-gate-framework`). Blocked by SHIP-415 (`feat-soul-gate-framework`, done).

## Problem / Goal

The Researcher has 12 Exa calls per run and spends them on whatever the model types. A vague query ("competitors", "market size"), a repeat of an earlier query, or a topic the competitor KB already answers each use up a call and add noise to the snapshot.

Goal: every `web_search_exa` and `web_fetch_exa` call passes an input gate from the shared gate framework first. Code checks run first (the same query or URL was not already used). Then a judge decides whether the topic is specific, fills a gap in what the run has saved, and is not already answered by the KB. A rejected call makes no Exa call and spends no budget; the model gets the reason and may revise. After 2 retries the call is skipped and the Researcher goes on with what it has.

## User stories

1. As a founder, I want my Exa calls spent on specific topics, so that the research is about my idea and not about a whole market.
2. As a founder, I want no search repeated, so that the budget reaches more topics.
3. As a founder, I want no search for what the competitor KB already answers, so that research is faster and cheaper.
4. As a founder, I want a search that fills a gap in what is saved to run without delay, so that good research is not slowed by checks.
5. As a founder, I want a gate never to fail my run, so that a quality check cannot cost me my work.
6. As a founder, I want research to finish with what it has when a search is skipped, so that I still get a snapshot and a score.
7. As the Researcher, I want the reason a search was refused, so that I can name a more specific topic.
8. As the Researcher, I want a skipped search to say so and tell me to go on, so that I do not loop on the same query.
9. As the Researcher, I want a refused search not to spend the call budget, so that retries do not eat the 12 calls.
10. As the Researcher, I want a fetch of a page already fetched or already saved refused, so that I do not read it twice.
11. As the Researcher, I want to see what the KB matched for a query, so that I know why a search was judged redundant.
12. As the Scorer and Advisor, I want the snapshot to hold specific sources, so that scores cite evidence that matters.
13. As an operator, I want every Researcher gate decision in run events and traces, so that I see why a search was refused or skipped.
14. As an operator, I want a run that is out of Exa calls to behave as before, so that the cap is unchanged.
15. As a developer, I want the input gate to be a `Gate` value over the shared framework, so that no retry logic is written again.
16. As a developer, I want the near-duplicate rule shared with the Interviewer's gate, so that two copies do not drift.
17. As a developer, I want frozen gate eval cases for the Researcher, so that a prompt or model change that weakens the gate shows up in CI.
18. As a developer, I want the prompt change as a new version file (`researcher.v3.md`), so that runs trace to the exact text.
19. As an operator, I want a judge error or an exhausted judge cap to let the call through, so that a flaky judge never blocks research.

## Requirements

1. **Gate.** Add one input gate `research_input` (specialist `researcher`) over the shared framework in `metis.agent.gate`. Its item says which tool is called (`web_search_exa` or `web_fetch_exa`) and the query or URL. Search and fetch each keep their own retry slot in the `GateContext` (keyed by tool name).
2. **Wiring.** Both Exa tools pass the gate before the call cap. The gate sits outside `with_call_cap`, so a refused or skipped call never reaches the budget counter. A refusal is a `GateRefusal` listed in the Researcher loop's `refusals`; the model gets the reason as a tool error and may revise. The Researcher builds one `GateContext` per invocation (`build_gate_context`).
3. **Spent budget first.** Before the gate runs, a spent call budget is answered with `CAP_MESSAGE` exactly as today: no gate event, no judge call. This needs a read-only check on `ExaCallBudget` that does not spend a call. (The issue lists "budget not spent" as a code check; it is kept first but stays outside the retry rule because a spent budget never recovers.)
4. **Code check: duplicate search.** A search whose normalised query is a near-duplicate of a query already run in this run is rejected (reason names the earlier query). Near-duplicate uses the word-set similarity rule of the Interviewer's input gate (≥ 0.8); the rule moves to a small shared helper and both gates use it. Queries and URLs are remembered per run in Redis once Exa has answered the call (same TTL as the Exa cache), so a node re-run after a crash shares them.
5. **Code check: duplicate fetch.** A fetch of a URL already fetched in this run, or already saved as a research item or competitor of the run's snapshot, is rejected. URLs are compared normalised (lowercase host, no fragment, no trailing slash, no tracking parameters).
6. **Judge.** After the code checks pass, the judge sees: the tool and its query or URL, the idea title and text, the interview brief, what the run's snapshot already holds (competitor names, item kind, title and claim), and the KB matches for the query (see 7). Instruction, rejecting when: (a) a search is not specific (a bare category such as "competitors" or "market size", with no product, company, segment or claim named); (b) it does not fill a gap (what is saved already answers it, or it has nothing to do with this idea); (c) the KB matches already answer it; (d) for a fetch, the page would add nothing to what is saved. The judge replies `PASS` or `REJECT: <reason>` as in SHIP-415.
7. **KB matches.** Before the judge call, the gate's builder looks up the query in the competitor KB with the same read the `kb_lookup` tool uses (embeddings, with the name or domain fallback) and gives the top matches (name, domain, description, pricing) to the judge. A failing lookup is logged and the judge runs without matches. No new KB behavior is added: the read inside the `kb_lookup` tool is extracted into `find_kb_matches` (same code, no change to the tool) and the gate calls it.
8. **Retry and skip.** Both decisions follow the framework: a rejection returns its reason to the model as a refusal; after 2 retries (3 attempts) the call is skipped. A skipped call answers: the search or fetch was not made and why, and the model should go on with what it has and call `finish_research` when done. The retry count of a slot resets only when a call of that tool passes (after a skip, the next rejected call of that tool is skipped at once). A skip is never a failure and never sets `last_error`; a run whose searches were all skipped still closes its snapshot and ends `succeeded`.
9. **Fail open.** A judge error, an unreadable reply, or the exhausted per-run judge cap (`GATE_JUDGE_MAX_CALLS_PER_RUN`, shared with the run's other gates) lets the call through. A failing code check never fails open.
10. **Events and spans.** Gate decisions are published and traced by the framework; nothing new is added. `specialist` is `researcher`, `gate` is `research_input`. The existing `tool_call` events of the Exa tools are unchanged and are not emitted for refused or skipped calls.
11. **Prompt.** Add `researcher.v3.md` (do not edit v1 or v2) and switch the Researcher to it. It tells the model to name a specific product, company, segment or claim in each search, to call `kb_lookup` first, to read a refusal as a request for a more specific topic, and to go on when a call is skipped. The soul is prepended by `load_specialist_prompt`, so no tone rules are repeated.
12. **Gate evals.** Add frozen Researcher cases under `server/evals/gates/` (valuable searches that must pass, vague or redundant ones that must be rejected; each freezes the idea text, the brief, the saved items, the KB matches and the candidate call) and extend `python -m evals.run_gates` with `--specialist interviewer|researcher` (default: both) and a recorded-verdict replay file for the new cases. The existing `evals.yml` recorded gate step keeps running; the real-model job covers both.
13. **Docs.** Update `server-context.md` (the Researcher gate, `researcher.v3`, the budget peek, the shared near-duplicate helper). `architecture.md` changes only if an invariant does. Add a row to Decisions in `progress-tracker.md`.

## Seams (how this is tested)

The highest seam is the Researcher's gated Exa tools (the same wrapper the loop receives) called with fake Exa tools, a fake judge, a fake Redis and the existing Researcher test harness (`tests/agent/test_researcher.py`). It covers code checks, the judge, retries, skips, the budget, KB matches and events in one place, and proves that a refused call makes no Exa call. The gate evals use the framework's public `run_gate` with a recorded or real judge (the seam SHIP-415 and SHIP-416 already use). No lower seams are added.

## Out of scope

- Gates on the other specialists, including the Scorer and the Advisor, which also search Exa.
- Gates on `kb_upsert_competitor` and `save_research_item` (output gates for saved findings).
- Changing the Exa call cap (12), the Exa cache, `kb_lookup` or the research module.
- Any web change, including how skipped searches are displayed.
- Changing the soul or the gate framework (SHIP-415).

## Touches

- `server/metis/agent/tools/exa.py` (gate wrapper, budget peek), a new `agent/tools/research_gates.py` (the gate and its item builder)
- `server/metis/agent/specialists/researcher.py` (gate context, refusals, prompt v3)
- `server/metis/agent/tools/interview_gates.py` (use the shared near-duplicate helper), `server/metis/agent/tools/research_kb.py` (extract `find_kb_matches`), `server/metis/agent/text_match.py` (new)
- `server/metis/prompts/` (`researcher.v3.md`)
- `server/evals/` (Researcher gate cases, runner option, recorded verdicts), `.github/workflows/evals.yml` (only if the real-model step needs the new option)
- `server/tests/agent/`, `server/tests/evals/`
- `.agents/ctx/server-context.md`

## Dependencies

- `feat-soul-gate-framework` (SHIP-415): done.
- `feat-interviewer-gates` (SHIP-416): done; shares the near-duplicate rule.

## Acceptance criteria

- A vague search makes no Exa call, spends no call from the budget, and the model gets the reason.
- A duplicate search or a duplicate fetch makes no Exa call.
- A search the KB already answers makes no Exa call.
- A specific search that fills a gap runs and is counted once.
- After 2 refused revisions the search is skipped, the Researcher goes on, and the run still ends `succeeded` with a closed snapshot.
- A spent call budget answers as before (no gate event, no judge call).
- A judge error, unreadable reply or exhausted judge cap lets the call through; a failing code check still rejects it.
- Gate decisions appear as `gate` run events with `specialist: researcher`.
- `ruff`, `mypy`, `lint-imports` pass. Gate evals pass in CI (tests run by CI, not locally).

## Open questions

None. Resolved on 2026-11-28 (user chose the recommended option each time): the gate looks up the KB itself and shows the matches to the judge (requirement 7); a spent budget is answered before the gate (requirement 3).

## Status

done
