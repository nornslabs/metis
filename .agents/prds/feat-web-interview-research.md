# PRD: feat-web-interview-research

Linear: SHIP-239 · https://linear.app/heimdallabs/issue/SHIP-239/22-web-interview-chat-and-research-panel

Milestone: M3 — Interview and discovery. Branch: `feat/web-interview-research`. Blocks SHIP-245 (web score card). Related: SHIP-255 (approval interrupts are used by export), SHIP-229 (research API).

## Problem / Goal

The Interviewer (SHIP-236) and Researcher (SHIP-238) run on the server and the run view (SHIP-235) streams them, but the idea page can only show a question as a read-only placeholder: the composer is disabled ("Answering comes soon"), nothing calls `POST /v1/runs/{id}/resume`, and research is never shown. A user cannot finish an interview or see what the Researcher found.

Goal: on `/ideas/[ideaId]` the user answers each interview question in the same thread and composer, the run continues, and when research finishes the user can browse competitors and market facts, each with a clickable source. A reload mid-interview restores the thread and the pending question.

## User stories

1. As a user whose run asks a question, I want the question shown as an agent message, so that I know what Metis needs.
2. As a user, I want the composer enabled while a question is pending, so that I can answer in the chat.
3. As a user, I want Enter to send my answer and Shift+Enter to add a line, so that I can write longer answers.
4. As a user, I want an answer of 1–10,000 characters validated before sending, with a short inline message, so that I know what to fix.
5. As a user, I want my answer to appear at once as my message, so that the chat feels responsive.
6. As a user, I want the composer disabled and a shimmer shown while the agent works on my answer, so that I know it is not stuck.
7. As a user, I want the streamed agent text to appear as it is written, so that I can read along.
8. As a user, I want a "Skip" quick reply, so that I can pass on a question I cannot answer.
9. As a user, I want a "That's enough" quick reply, so that I can end the interview early.
10. As a user, I want a quick reply to send immediately, so that I do not need a second click.
11. As a user who answers twice (double click, two tabs), I want a clear message instead of a broken page, so that I can carry on.
12. As a user who reloads mid-interview, I want the thread and the pending question restored, so that I lose nothing.
13. As a user who reloads mid-interview, I want my earlier answers shown, so that I see the whole conversation (from the interview turns API).
14. As a user, I want an approval request shown with Approve and Reject buttons, so that I can allow or refuse an outside write.
15. As a user who approves or rejects, I want the choice shown in the thread and the run to continue, so that I see the result.
16. As a user, I want "Researching…" with the current tool name while the Researcher works, so that I know what it is doing.
17. As a user, I want the research view to appear when the Researcher step finishes, so that I do not have to reload.
18. As a user, I want each competitor shown with name, link, favicon letter, what it does, pricing and overlap, so that I can compare them.
19. As a user, I want each market fact shown with its quote, source link, date and confidence, so that I can judge it.
20. As a user, I want every competitor and fact to have a clickable source that opens in a new tab safely, so that I can verify it.
21. As a user, I want source chips under the agent message (favicon letter + domain, "+N more"), so that I see where the facts came from.
22. As a user, I want the research block collapsible, so that it does not push the chat away.
23. As a user, I want an empty state before research exists and a retry-able error state if loading fails, so that the page never looks broken.
24. As a keyboard user, I want to answer, skip, approve and open the research block without a mouse, so that I can use everything.
25. As a screen-reader user, I want new questions and research announced politely, so that I follow progress without focus jumping.
26. As a phone user (375px), I want the research block stacked under the chat with no horizontal scroll, so that I can use it on mobile.
27. As a user whose session expires, I want the usual "Signed out" toast and redirect, so that I can sign in again.
28. As a user, I want agent and source text rendered safely, so that nothing in it can run script.

## Requirements

1. **Answer a question.** While the run is `awaiting_user` with `pending_interrupt.type = "question"`, the idea page `Composer` is enabled (placeholder "Type your answer") and the question is shown as an agent message. The answer is validated with a Zod schema (trimmed, 1–10,000 characters; same rule as the server's resume check) and sent as `POST /v1/runs/{id}/resume {value: <text>}`. Enter sends, Shift+Enter adds a line. Inline error under the textarea.
2. **Quick replies.** Chips above the composer while a question is pending: "Skip" sends `skip`, "That's enough" sends `that's enough` (the server's `SKIP_ANSWER` and `STOP_ANSWERS`). They send at once. No topic or suggestion chips: the question payload carries no suggestions.
3. **After sending.** Optimistic `UserBubble` with the answer; the composer is disabled and a `Shimmer` shows until `run_status: running` is seen, then `token` text streams. If the run reaches `awaiting_user` again, the next question appears and the composer re-enables. A failed resume removes the optimistic bubble and shows the error inline.
4. **Resume errors.** `409 run.invalid_state` refetches the run (`useLatestRun`) and shows "This run already moved on." A `422` maps to the field error. Other errors use `describeError`.
5. **Reload restore.** The run view seeds `pending_interrupt` (already done by `useRunEvents`); the page shows the pending question and an enabled composer. Earlier questions and answers come from `GET /v1/ideas/{id}/interview` (server PRD, see Dependencies), shown as agent and user messages in order.
6. **Approval interrupts.** `{type: "approval", action, details}` shows `action` and `details` with Approve and Reject buttons; each resumes with `{value: true|false}`; the choice appears as a user message ("Approved" / "Rejected"). The interrupt schema in `lib/events/schemas.ts` keeps `details` (not read today).
7. **Researching state.** While a `Researcher` step runs, `StepList`/`Shimmer` show "Researching…" with the latest `tool_call` name from that step.
8. **Research view.** `useResearch(ideaId)` over `GET /v1/ideas/{id}/research` (`ResearchView`: `summary`, `items`, `competitors`); `404 research.not_found` is the empty state, not an error. It refetches when `node_finished` arrives for the `researcher` node and when the run ends. Competitor card: name, link (`url`, `rel="noopener noreferrer" target="_blank"`), favicon letter, `description`, `pricing`, `overlap` as a percentage. Market fact (`kind = market_fact`): `claim`, `quote`, source link (`url`), `published_at`, `confidence`. Trends and risks (`kind = trend | risk`) listed with their claim when present. Every competitor and fact must show a clickable source; an item with no valid URL is not shown as sourced (the server rejects this, so it should not happen).
9. **Sources chips.** Under the agent message, square chips (favicon letter + domain, "+N more" past a limit) built from the fetched research items. The server emits no `research.item` events yet, so chips appear after the research view loads, not while it streams.
10. **Where research shows.** A collapsible block inside the agent message, plus `Sources` chips; mobile stacks naturally because it is in the thread.
11. **States.** Empty (no research yet), loading (square skeleton), error with Retry, interview ended. Keyboard order: thread → quick replies → composer.
12. **Components.** `components/chat/`: `Composer` gains an answer mode, `QuickReplies`, `ApprovalPrompt`, `QuestionMessage`; `components/research/`: `ResearchPanel`, `CompetitorCard`, `MarketFactRow`, `Sources`. Tokens only, square, light and dark per the samples.
13. **Hooks and schemas.** `useResumeRun` mutation, `useResearch` query (workspace-scoped key in `keys.ts`), `lib/schemas/answer.ts`. All on the generated client; the web `schema.d.ts` already has the research routes.
14. **Docs sync.** `ui-context.md`: Composer (answer mode, quick replies), Sources, a Research section (location, states), Live Run Events (`interrupt` details; research arrives by refetch).

## Out of scope

- The score card, history and suggestions (SHIP-245, M4).
- The export approval flow itself (SHIP-255); only the generic approval prompt ships here.
- Topic coverage chips (no server field).
- Live source chips from `research.item` events (the server does not emit them).
- Editing or deleting research items.
- Any server change (the interview turns API is its own PRD).

## Touches

- `web/app/(app)/ideas/[ideaId]/**`
- `web/components/chat/**`, `web/components/research/**` (new)
- `web/lib/events/schemas.ts` (keep approval `details`), `web/lib/api/queries/`, `web/lib/api/mutations/`, `web/lib/schemas/`
- `web/e2e/` (new spec + support)
- `.agents/ctx/ui-context.md`
- `.agents/progress-tracker.md`

## Dependencies

- `feat-web-ideas-runs` (SHIP-235): done.
- `feat-exa-researcher` (SHIP-238): done on `feat/exa-researcher`, not merged yet; the real interview and research need it.
- `feat-research-module` (SHIP-229): done (PR #45 merged).
- `feat-interviewer` (SHIP-236): done.
- `feat-runs-api` (SHIP-232), `feat-run-events-sse` (SHIP-234): done.
- `feat-interview-turns-api` (SHIP-270): `GET /v1/ideas/{id}/interview` (past interview turns); draft, must be `done` first.

## Testing

Same two seams as `feat-web-ideas-runs` (proposed; no new seam):

1. **Browser seam (primary):** Playwright on the compose stack with `AGENT_STUB_SPECIALISTS=true`. Stub runs never ask, so `page.route` fakes `/v1/runs/*/events`, `GET /v1/runs/*` and `POST /v1/runs/*/resume`, and `GET /v1/ideas/*/research`.
   - Question shown, composer enabled; Enter sends `{value}`; Shift+Enter adds a line; optimistic bubble; composer disabled until `run_status: running`.
   - Quick replies send `skip` and `that's enough`.
   - 409 `run.invalid_state` refetches and shows the message; resume failure removes the bubble.
   - Reload with a pending question restores question and composer.
   - Approval: Approve sends `true`, Reject sends `false`.
   - Research: empty on 404; after `node_finished` for `researcher` the competitors and facts render with working links (`target="_blank"`, `rel` set); a source chip per domain.
   - Visual: 1280px and 375px, light and dark, no horizontal scroll.
2. **Pure-function seam:** Vitest on `lib/schemas/answer.ts` (length rules), the reducer (approval `details`, tool name for the current step) and research view mapping (domain, overlap %, confidence label, "+N more").

No component unit tests. `npm run lint`, `typecheck`, `build` pass.

## Acceptance criteria

- [x] A user completes an interview entirely in the chat (answer, skip, "That's enough").
- [x] Every competitor and fact shows a clickable source.
- [x] Reload mid-interview restores the chat and the pending question.
- [x] Approval interrupts resume with a boolean.
- [x] The research view appears when the Researcher finishes, with empty and error states.
- [x] Every form and SSE payload is validated with Zod; agent text is sanitized markdown.
- [x] Light and dark match the samples; works at 375px.
- [x] `ui-context.md` synced.
- [x] `npm run lint`, `typecheck`, `build` pass; Vitest and Playwright specs above pass.

## Open questions

None open for this PRD. One blocker sits outside it: the server PRD for interview turns (see Resolved 1) does not exist yet.

## Resolved (user, 2026-11-19)

1. Past answers: a separate server PRD adds `GET /v1/ideas/{id}/interview` (turns: topic, question, answer, run id) first; this PRD depends on it and shows earlier turns from it (stories 12–13, requirement 5). Web and server stay split.
2. Research location: Sources chips plus a collapsible research block inside the agent message; no side panel. Added to `ui-context.md` as part of this PRD.
3. Quick replies: static "Skip" and "That's enough" only; no suggestion chips.

## Built (2026-11-19)

- Stacked on `feat/interview-turns-api` (PR #47 not merged yet; user decision), so the SHIP-239 PR must merge after it or target it.
- Interview thread: questions and answers come from `GET /v1/ideas/{id}/interview` plus the run's current question; an answer sent from the page shows at once (`sent`) and is taken back on failure. The composer waits for the turns before enabling an answer, so a replayed old question never looks pending.
- Added beyond the spec, small: a "Stop run" button next to the quick replies (while a question is pending the send button is Send, so Stop needed another place; an unanswered run would block retry); the research error alert shows only once a Researcher step has started.
- Approval choice ("Approved" / "Rejected") shows from local state, so it is not restored after a reload.
- `lib/events/schemas.ts` keeps approval `details` (a string; other shapes are dropped). `InterruptPlaceholder` is removed.
- Tests: Vitest 150 (new: `lib/schemas/answer`, `lib/events/activity`, `lib/interview/thread`, `lib/research/view`, approval details); Playwright 51, of which 15 are new in `e2e/interview-research.spec.ts` (answers, quick replies, 409 and failed resume, reload restore, noted turns, approval, research view, unsafe link, 375px). Run against `next dev` on :3001 with the compose API on :8000 (its image predates the new routes, so the interview and research calls are faked with `page.route`, as the PRD plans).
- Not covered: a real interview with the real LLM (the stack has no LLM key).

## Status

done
