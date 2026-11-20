# PRD: feat-web-score-card

Linear: SHIP-245 · https://linear.app/heimdallabs/issue/SHIP-245/28-web-score-card-history-and-suggestions

Milestone: M4 — Scoring and advice. Branch: `feat/web-score-card`. Blocks SHIP-247 (web spec editor). Related: SHIP-227 (scoring API), SHIP-240 (Scorer), SHIP-241 (Advisor), SHIP-242 (manual refresh runs), SHIP-239 (interview and research UI).

## Problem / Goal

The Scorer and Advisor run on the server and store a score (six parameters, each with reason, evidence and confidence), history and suggestions, but the web shows none of it. The `score` run event is ignored, and an `advise` run (score below 55) pauses on an `advice_decision` interrupt that the page cannot answer, so the run stays `awaiting_user` forever. A user cannot see why an idea got its score, cannot act on the advice, and cannot refresh the score.

Goal: on `/ideas/[ideaId]` the user sees the total, band and six evidence-backed parameter scores, the history of scores, and suggestions they can accept or dismiss. When the run waits on `advice_decision` they can revise and rescore, continue to the spec, or stop. "Re-check market" and "Rescore" refresh the card without a reload.

## User stories

1. As a user, I want my idea's total score out of 100 with its band (Build, Promising, Advise) after scoring, so that I know the verdict at a glance.
2. As a user, I want the band shown as a label as well as a color, so that I can read it without relying on color.
3. As a user, I want to see "Last checked N days ago", so that I know how fresh the score is.
4. As a user, I want six parameter bars, each with label, weight, raw mark out of 10 and weighted points, so that I see where the score comes from.
5. As a user, I want to click a parameter to see its reason, evidence quotes with source links and confidence, so that I can judge whether to trust it.
6. As a user, I want a parameter scored without evidence marked "No evidence" with its low confidence, so that guesses are not passed off as facts.
7. As a user, I want evidence links to open in a new tab safely and only when they are http(s), so that nothing unsafe can run.
8. As a user, I want the bars to animate on first show, and not when I have reduced motion on, so that the page respects my settings.
9. As a user, I want the card to appear as soon as the Scorer finishes, with no reload, so that the chat feels live.
10. As a user, I want a reload to show the same card, so that I lose nothing.
11. As a user, I want a small line chart of my totals across score runs, so that I see whether revisions help.
12. As a user, I want to select two score runs and see per-parameter deltas with each side's reason, so that I understand what changed.
13. As a user with one score run, I want a plain "One score so far" instead of an empty chart, so that the page never looks broken.
14. As a user whose idea is below 75, I want suggestion cards by kind (feature, niche, pricing, pivot) with rationale, target parameters and sources, so that I know how to improve it.
15. As a user, I want to Accept or Dismiss a suggestion and have it stay that way after reload, so that my choices are kept.
16. As a user, I want to undo an Accept or Dismiss, so that a misclick costs nothing.
17. As a user whose run waits on `advice_decision`, I want to see the score, the suggestions and three options, so that I can decide what happens next.
18. As a user, I want "Revise idea and rescore" to let me edit the idea text and list the accepted suggestions that will be added, so that I control the revision.
19. As a user, I want a revised idea checked for length (10–10,000 characters) before sending, so that I know what to fix.
20. As a user, I want "Continue to spec anyway" and "Stop here" to answer the run at once, so that I am not blocked.
21. As a user, I want my decision shown in the thread, so that I see what I chose.
22. As a user, I want a rescored result after revising to show on the card and in the chart, so that I see the effect.
23. As a user, I want "Re-check market" to start a fresh market check and score, so that the score reflects new research.
24. As a user, I want "Rescore" to score again on the research I already have, so that a revision or a changed answer is reflected without new searches.
25. As a user, I want both refresh buttons disabled while a run is active or when the LLM key is not ready, with the reason shown, so that I never start a rejected run.
26. As a user without a closed research snapshot, I want a clear message when I try to re-check, so that I know what to do first.
27. As a user, I want the card and history to update when a refresh run ends, so that I do not reload.
28. As a keyboard user, I want every bar, chart point, comparison pick and button reachable and operable by keyboard, so that I can use all of it.
29. As a screen-reader user, I want the total, band and each parameter's value announced as text, so that the chart and bars are not the only source.
30. As a phone user (375px), I want the card, chart and suggestions stacked in one column with no horizontal scroll, so that I can use it on mobile.
31. As a user, I want light and dark to match the design samples, so that the card looks like the rest of the app.
32. As a user whose session expires, I want the usual "Signed out" toast and redirect.

## Requirements

1. **Where it shows.** A `ScoreSection` in the idea page's agent message for the latest run, under the research block. It reads the idea's score, not the run's: `GET /v1/ideas/{id}/scores/latest` (`404 score.not_found` is the empty state, not an error), `GET /v1/ideas/{id}/scores` (history, newest first) and `GET /v1/ideas/{id}/suggestions`. Hooks `useLatestScore`, `useScoreHistory`, `useSuggestions` in `lib/api/queries/`, workspace-scoped keys in `keys.ts`.
2. **`ScoreCard`.** Total out of 100 (`text-score`, tabular, `/ 100` muted), `BandBadge` (`build` success, `promising` warning, `advise` destructive; label text "Build" / "Promising" / "Advise"), "Last checked N days ago" from `created_at` ("today" under a day), the two refresh buttons (requirement 8), then six `ParamBar`s in server order.
3. **`ParamBar`.** Row: label, weight (`weights`), raw/10 bar on a `h-track` track (width animates on mount, 800 ms; no animation under `prefers-reduced-motion`), weighted points (`weighted`). The row is a button (`aria-expanded`) that opens a detail block: `reason` (plain text), confidence as High / Medium / Low plus the number (same mapping as research facts), evidence items (title, quote, source link) or "No evidence" when `no_evidence`. Source links are http(s) only with `target="_blank" rel="noopener noreferrer nofollow"`, reusing `SourceLink`.
4. **Live refresh.** The `score` event (`{score_run_id, total, band}`) gets a Zod schema in `lib/events/schemas.ts` and a reducer field; when a new `score_run_id` arrives the three score queries are invalidated. The queries are also invalidated when a run ends. The card never renders from event data; it is a refetch trigger (the event carries no params).
5. **History.** `ScoreHistoryChart`: a hand-built inline SVG line of `total` over score runs (oldest left), 0–100 axis with band thresholds at 55 and 75 as faint lines, one focusable point per run with a tooltip (total, band, date, trigger). No chart dependency. A list under it shows each run (date, total, band) with a checkbox; selecting exactly two enables "Compare", which fetches both runs (`GET /v1/scores/{id}`) and shows a table of the six parameters: raw of the older, raw of the newer, delta (signed), and each side's reason. The diff is computed in the web (see Decisions). Fewer than two runs: "One score so far".
5. **Suggestions.** `SuggestionList` shows the newest score run's suggestions (the list endpoint returns newest run first; group by `score_run_id`, show the first group, older groups collapsed under "Earlier suggestions"). Card: kind chip, `title`, `rationale`, target parameters (labels), `expected_impact`, evidence source links, status. Accept and Dismiss call `PATCH /v1/suggestions/{id}` `{status}`; the buttons toggle (an accepted suggestion shows "Accepted" and an Undo that sets `open`). Shown when the latest band is `advise` or `promising`, and whenever suggestions exist.
6. **Advice decision.** When the run is `awaiting_user` with `pending_interrupt.type = "advice_decision"` (stream or run view), show `AdviceDecision` under the card: the score and band, three buttons answering `POST /v1/runs/{id}/resume`:
   - **Revise idea and rescore:** opens an inline editor prefilled with the idea's `raw_text` (10–10,000 characters, Zod, same rule as the server), a list of the accepted suggestions of the advised score run that will be added (at most 5, the first five), and a Send button. Resume value `{decision: "revise", revised_text, accepted_suggestion_ids}`. The server applies the revision to the idea and appends the accepted suggestions; the web does not call `PATCH /v1/ideas/{id}`.
   - **Continue to spec anyway:** `{decision: "continue"}`.
   - **Stop here:** `{decision: "stop"}`.
   The choice shows in the thread as a user message ("Revise and rescore" / "Continue to spec" / "Stop here"). `409 run.invalid_state` refetches the run and says "This run already moved on."; `422` shows the server detail; other errors use `describeError`. The `advice_decision` interrupt payload (`{type, score_run_id, total, band, suggestion_ids}`) gets a Zod schema in `lib/events/schemas.ts` (today ignored) and the reducer keeps it as an interrupt kind; the Composer shows "Decide above" while it waits.
7. **Refresh actions.** "Re-check market" calls `POST /v1/ideas/{id}/recheck-market`, "Rescore" calls `POST /v1/ideas/{id}/rescore`; both send a fresh `Idempotency-Key` and no body, return `{run_id}`, then refetch the idea's latest run so the page follows it (a refresh run is the idea's latest run, so `useRunEvents` takes over). Both are disabled while any run of the idea is active (`queued`, `running`, `awaiting_user`) and when the LLM key blocks a run (`useKeyGate`, same text). Errors: `409 run.already_running` → "A run is already in progress for this idea." and refetch; `402 provider.llm_not_ready` → the key-gate text; `404 research.not_found` on a re-check → "Run research first: there is no finished research to re-check."; others `describeError`.
8. **Run view of a refresh run.** A `rescore` / `market_recheck` run renders like a pipeline run: steps, notices, then the `ScoreSection` (which already shows the new score). Nothing else changes in the thread.
9. **States.** No score yet: nothing (the steps show progress). Loading: square skeletons. Load error: alert with Retry. Empty suggestions on a `build` idea: not shown.
10. **Components.** `components/score/`: `ScoreSection`, `ScoreCard`, `ParamBar`, `BandBadge`, `ScoreHistoryChart`, `ScoreCompare`, `RefreshActions`; `components/suggestions/`: `SuggestionList`, `SuggestionCard`; `components/chat/`: `AdviceDecision` (decision buttons and revise editor), wired in `RunConversation`. Tokens only, square, 1px lines, shadcn + Tailwind only. New fixed sizes go in the `@theme` block and `lib/cn.ts` (see Custom Lengths).
11. **Pure helpers.** `lib/scores/`: `view.ts` (band label and token, confidence label, "N days ago", param label, series for the chart), `diff.ts` (per-parameter delta of two `ScoreRun`s), `decision.ts` (Zod for the revise form, resume value builder).
12. **Docs sync.** `ui-context.md`: Folder Structure (`components/suggestions/`, `lib/scores/`), Components (`ScoreCard`, `ParamBar`, `BandBadge`, `ScoreHistoryChart`, `ScoreCompare`, `SuggestionList`, `AdviceDecision`, `RefreshActions`), Live Run Events (`score` and `advice_decision` now used; `score.param` / `score.completed` do not exist), a Scores section (where it shows, refetch rules, decision flow), `Suggestions` row renamed so it is not confused with the empty-chat chips. The `server-context.md` line "web has no UI for `advice_decision` yet" is updated.

## Out of scope

- Public share cards and a leaderboard.
- Any server change: no new route, no migration (compare is computed in the web; revision goes through the resume payload).
- Editing the idea outside the advice decision, the spec editor (SHIP-247), the Architect (SHIP-244).
- Scheduled or signal-triggered rescoring and alerts.
- Live per-parameter events (the server emits one `score` event only).
- A score view outside `/ideas/[ideaId]` (no list-screen badge).

## Touches

`web/components/score/`, `web/components/suggestions/`, `web/components/chat/` (RunConversation, ConversationLayout wiring, Composer placeholder), `web/lib/scores/`, `web/lib/api/queries/` and `mutations/`, `web/lib/events/` (schemas, reducer), `web/e2e/`, `web/app/globals.css` and `web/lib/cn.ts` (new lengths if needed), `.agents/ctx/ui-context.md`, `.agents/ctx/server-context.md` (one line).

## Dependencies

Done: feat-scorer (SHIP-240), feat-advisor (SHIP-241), feat-manual-rescore (SHIP-242, merged in PR #63), feat-web-interview-research (SHIP-239), feat-scoring-module (SHIP-227). Web `schema.d.ts` already has the scores, suggestions, rescore, recheck-market and resume routes (regenerate if `npm run gen:api` shows a diff).

## Acceptance criteria

1. After a run scores an idea, the card shows total, band label, "Last checked", and six bars with label, weight, raw/10 and weighted points, with no reload and again after a reload.
2. Clicking each of the six bars shows reason, confidence and evidence (or "No evidence"); evidence links are http(s) only and open safely.
3. Below 55 the run pauses on `advice_decision`: the user sees the score, three to five suggestions and the three decision options; each option resumes the run correctly (revise sends `revised_text` 10–10,000 characters and at most 5 accepted ids; the rescored card replaces the old one without reload).
4. Accept, Dismiss and Undo persist across reload.
5. History shows one point per score run; selecting two runs shows signed per-parameter deltas with both reasons.
6. "Re-check market" and "Rescore" start a run, are disabled while a run is active or the LLM key blocks, map their errors as above, and the card and history update when the run ends.
7. Light and dark both match `design/samples/` (bands: success, warning, destructive); the bar animation is off under `prefers-reduced-motion`; layout has no horizontal scroll at 375px.
8. Every interactive part works by keyboard; the total, band and parameter values are available as text.
9. `npm run lint`, `npm run typecheck`, `npm run build` pass; Vitest and Playwright specs for the behavior above are written (run by CI, not locally).

## Testing

Seam: one, the browser, as in SHIP-235 and SHIP-239. Playwright specs on the compose stack use `page.route` to fake the score, history, suggestion, run and SSE responses (the stub specialists never score, and a real score needs an LLM) and check what the user sees and sends: card content, bar detail, history and compare, suggestions toggling, the three decisions and their resume bodies, refresh buttons and their errors. Vitest covers the pure `lib/` code only: `lib/scores/view.ts`, `diff.ts`, `decision.ts`, and the event schemas and reducer for `score` and `advice_decision`. Tests check behavior (text, requests sent), not component internals. Prior art: `web/e2e/idea-chat.spec.ts`, `web/e2e/interview-research.spec.ts`, `web/lib/events/*.test.ts`.

## Decisions

Answered 2026-11-20 (all recommended):

1. **Compare:** computed in the web from two `GET /v1/scores/{id}` calls; no server route.
2. **Revision:** resume payload only (`revised_text`, `accepted_suggestion_ids`); no `PATCH /v1/ideas/{id}`.
3. **Refresh buttons:** both, "Re-check market" and "Rescore".
4. **History chart:** hand-built SVG, no new dependency.

## Status

done
