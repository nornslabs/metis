# PRD: feat-advisor-gate

Linear: SHIP-418 · https://linear.app/heimdallabs/issue/SHIP-418/advisor-gate

Parent: SHIP-414. Branch: `feat/advisor-gate` (base to confirm when building: `main` if the soul and gate framework, SHIP-415, is merged there; otherwise stacked on the branch that carries it). Blocked by SHIP-415 (`feat-soul-gate-framework`, done). Blocks nothing.

## Problem / Goal

The Advisor saves any suggestion that passes three code rules (count limit, a weak-parameter target, known URLs). Everything else lives only in `advisor.v2.md`: suggestions differ from each other, are specific rather than generic, do not repeat what the idea already does, and carry a quote that supports the claim. A model that drifts from the prompt saves a vague or duplicate suggestion and the user sees it.

Goal: every suggestion passes one output gate from the shared gate framework before it is saved. Code checks run first (targets a weakest parameter, differs from the suggestions already saved, every source URL known). Then the judge decides whether the suggestion would move the score, is specific, and is supported by its quote, in the soul's tone. A rejected suggestion is refused with its reason so the model can revise; after 2 retries it is skipped. Frozen gate evals prove strong suggestions pass and weak ones are rejected.

## User stories

1. As a founder, I want every suggestion to aim at a parameter that really holds my score back, so that advice goes where it helps.
2. As a founder, I want no two suggestions that say the same thing, so that the list is worth reading.
3. As a founder, I want every source link to be a page Metis actually saw, so that I never follow an invented URL.
4. As a founder, I want each suggestion's quote to support its claim, so that I can trust the reason given.
5. As a founder, I want specific suggestions (my niche, my price, my feature), so that I never read advice that fits any idea.
6. As a founder, I want suggestions that do not repeat what my idea already does, so that I get something new.
7. As a founder, I want a suggestion that would not move my score to be dropped, so that the list stays short and useful.
8. As a founder, I want the calm, plain tone of the soul in every suggestion (no flattery, hype or verdict), so that Metis sounds like one product.
9. As a founder, I want a weak suggestion revised or dropped before I see it, so that I only see good ones.
10. As a founder, I want a gate never to fail my run, so that a quality check cannot cost me my work.
11. As a founder with a score below 55, I want to still reach the decision step when the gate dropped some suggestions, so that I am not blocked by a quality check.
12. As an operator, I want every Advisor gate decision in run events and traces, so that I see why a suggestion changed or was dropped.
13. As a developer, I want the gate defined as a `Gate` value over the shared framework, so that no retry logic is written again.
14. As a developer, I want the rules that lived only in the prompt moved into code, so that a model change cannot silently drop them.
15. As a developer, I want the gate eval cases frozen in the repo, so that a prompt or model change that weakens the gate shows up in CI.
16. As a developer, I want the new prompt as a new version file (`advisor.v3.md`), so that runs trace to the exact text.
17. As a developer, I want the judge to fail open and the code checks never to, so that availability and safety are both kept.
18. As the Spec step, I want suggestions to keep their stored shape, so that nothing downstream changes.

## Requirements

1. **Gate.** Define `advice_output` as a `Gate` (specialist `advisor`) in a new `agent/tools/advice_gate.py`, next to `advice.py`, with a `review_suggestion` function the tool and the gate evals both call (the pattern of `interview_gates.py`). No retry logic is written; `run_gate` and `enforce_gate` from `agent/gate.py` do it.
2. **Code checks, in order** (a failing check rejects without a judge call, and never fails open):
   1. The suggestion targets at least one of the plan's weakest parameters (today's rule, moved into the gate).
   2. It differs from the other suggestions: its title is not a near-duplicate (same words in another order or case, word-set overlap at least 0.8) of any suggestion already saved for this score run, including saves from an earlier pass.
   3. Every source URL is in the run's `SourceBook` (the research, the score's evidence, or the Advisor's own search results), as today.
   The count limit (`plan.maximum`) is not a quality check: it stays a plain refusal before the gate and does not use a retry.
3. **Judge.** One instruction with three tests: (a) would it move the score, naming the targeted parameters; (b) is it generic, meaning it could be given to any idea unchanged, or does it only restate what the idea already does; (c) does the quote of each source support the claim it is cited for. The soul's tone check applies: reject flattery, hype, emoji, a verdict. The judge sees the suggestion (kind, title, rationale, targets, expected impact, evidence), the idea title and text, the weakest parameters with the score's reason and raw mark for each, and the titles already saved. The judge reads the quote only; it does not fetch the page.
4. **Where it runs.** Inside `save_suggestion`, before the suggestion is stored, after the count limit. A pass saves as today. A rejection with retries left raises `GateRefusal` (the reason is the model's message, "Nothing was saved. ...") so the model may revise. After 2 retries (3 attempts) the suggestion is skipped: the tool answers that it was skipped and the model continues with another suggestion or finishes.
5. **Retry slot.** Retries are counted per suggestion slot across rewordings (one key), and the count resets once a suggestion is settled (saved or skipped), as in the Interviewer.
6. **Gate context.** The Advisor builds one `GateContext` per node invocation (`build_gate_context`), passes it to `advice_tools`, and lists `GateRefusal` next to `AdviceRefused` in the loop's `refusals`. The judge uses the gateway's `gate` purpose and the per-run judge cap from SHIP-415. The judge fails open on its own error, an unreadable reply or a spent cap.
7. **Skips and the minimum.** A skipped suggestion does not count as saved. `finish_advice` keeps its rule (below 55 owes at least 3; the first refusal lets the model go on, the second closes it). The ledger counts gate skips. When a below-55 score ends short and at least one gate skip caused it and at least one suggestion is saved, the node accepts what is saved and goes on to `advice_decision`; otherwise it fails with `advice.invalid_submission` as today. A skip never sets `last_error`.
8. **Idempotence.** The node's re-run rule is unchanged: with enough suggestions saved it makes no model call, so no gate runs on a re-run.
9. **Prompt.** Add `advisor.v3.md` (do not edit v1 or v2). It keeps the job and the suggestion fields, states that each suggestion is reviewed before it is saved and a refusal says why, drops rules that are now enforced in code (the weak-target and source rules stay as guidance only, in one line each), and does not repeat tone rules (the soul is prepended). Switch the Advisor to v3; `tests/test_prompts` follows.
10. **Events and spans.** Published and traced by the framework; nothing new. `specialist` is `advisor`, `gate` is `advice_output`.
11. **Gate evals.** Add frozen cases under `server/evals/` with a runner (`python -m evals.run_advice_gate`) in the pattern of `evals.run_gates`: each case freezes the idea text, the score's weakest parameters with their reasons, the suggestions already saved, the known source URLs, and the candidate suggestion, with the verdict it must get (`pass` or `reject`, and for a rejection which check or judge test). Cases: strong suggestions that pass; generic, duplicate, wrong-target, unsourced (invented URL) and unsupported-quote ones that are rejected. Include a recorded-model replay for offline CI and a step in `.github/workflows/evals.yml` for the manual real-model job. Code-check cases need no model.
12. **Docs.** Update `server-context.md` (the Advisor gate, `advisor.v3`, skip rule). `architecture.md` only if an invariant changes. Add a Decisions row to `progress-tracker.md`.

## Seams (how this is tested)

One seam: the Advisor's `save_suggestion` tool, called through the existing Advisor test harness (`tests/agent/test_advisor.py`) with a fake chat model, a fake judge and the fake gateway. It covers the code checks, the judge, retries, skip, the minimum, the events and `last_error` in one place. The gate evals call the public `review_suggestion` with a recorded or real judge (the seam SHIP-415 and SHIP-416 already use). No lower seams are added.

Please confirm this seam matches what you expect.

## Out of scope

- Gates on any other specialist (SHIP-417 and the rest).
- Any web change (a display of skipped suggestions or gate reasons).
- Changing the soul, the gate framework (SHIP-415), the suggestion table or its API.
- Verifying a quote against the live page (the judge reads the quote only).
- Changing the `finish_advice` rule (the minimum and its two refusals stay).
- A second language, per-user tone.

## Touches

- `server/metis/agent/tools/advice.py`, `server/metis/agent/tools/advice_gate.py` (new)
- `server/metis/agent/specialists/advisor.py` (gate context, refusals)
- `server/metis/prompts/` (`advisor.v3.md`)
- `server/evals/` (advice gate cases, runner, recorded replay), `.github/workflows/evals.yml`
- `server/tests/agent/`, `server/tests/evals/`, `server/tests/test_prompts`
- `.agents/ctx/server-context.md`

## Dependencies

- `feat-soul-gate-framework` (SHIP-415): done.

## Acceptance criteria

- A suggestion with an invented URL, or with no weak-parameter target, is rejected by a code check without a judge call.
- A near-duplicate of a saved suggestion is rejected.
- A generic suggestion is rejected by the judge, and a specific, sourced one passes and is saved.
- A rejected suggestion is refused with its reason; after 2 retries it is skipped and nothing is stored for it.
- A judge error, bad reply or spent cap lets a suggestion through; a failing code check still rejects it.
- A skipped suggestion never sets `last_error`.
- Gate decisions appear as `gate` run events with `specialist: advisor`, `gate: advice_output`.
- Re-running the node with enough suggestions saved makes no gate or model call.
- Gate evals pass in CI (recorded replay offline).
- `ruff`, `mypy`, `lint-imports` pass. Tests run in CI, not locally.

## Open questions

None. Resolved on 2026-11-28 (user chose the recommended option each time):

1. A shortfall caused by gate skips is accepted when at least one suggestion is saved: the user still reaches `advice_decision`. The run fails with `advice.invalid_submission` as today when nothing is saved or no skip happened. (Requirement 7: the node counts gate skips in the ledger and applies this rule where it now checks `plan.minimum`.)
2. "Differs from the other suggestions" is a code check: title word overlap of at least 0.8 against all suggestions saved for the score run.

## Status

done
