# PRD: feat-web-ideas-runs

Linear: SHIP-235 · https://linear.app/heimdallabs/issue/SHIP-235/17-web-idea-chat-and-live-run-view

Milestone: M2 — Ideas and agent run engine. Branch: `feat/web-ideas-runs`. Blocks SHIP-239 (interview chat and research panel).

## Problem / Goal

After SHIP-219 (sign-in, typed client, shell) a user lands on an empty chat whose composer does nothing. The server can already create ideas (SHIP-218), start, cancel and list runs (SHIP-232) and stream run events over SSE (SHIP-234), but nothing in the web uses them. A user cannot submit an idea or see the agent work.

Goal: the user describes an idea in the composer on `/`, the idea and its first run are created, and `/ideas/[ideaId]` shows the run progressing live (steps, tool calls, streamed text, status), survives a reload or a dropped connection with no duplicate rows, and lets the user stop a run or retry a failed one. Specialists are still stubs, so the view shows steps and status changes; scoring, research and interview answering come later.

## User stories

1. As a signed-in user on `/`, I want to type my idea in the composer and press Enter, so that Metis starts working on it.
2. As a user, I want Shift+Enter to add a new line, so that I can write a longer description.
3. As a user, I want to click a suggestion chip to fill the composer, so that I can try Metis without thinking of an idea.
4. As a user, I want the composer to grow with my text up to a limit, so that I can see what I wrote.
5. As a user, I want too-short or too-long ideas caught before sending, with a short inline message, so that I know what to fix.
6. As a user, I want the idea's title taken from my text automatically, so that I do not have to fill a second field.
7. As a user, I want Send disabled while my idea is being submitted, so that I do not create it twice.
8. As a user, I want to land on the idea's page right after sending, so that I can watch it.
9. As a user, I want my idea text shown as my message at the top of the conversation, so that I see what Metis is working on.
10. As a user, I want an agent message with the Metis mark under my idea, so that I see Metis's reply in one place.
11. As a user, I want a shimmering label for the current step while nothing has streamed yet, so that I know the run is alive.
12. As a user, I want each specialist step to appear as a row with a spinner, turning into a check when it finishes, so that I see progress.
13. As a user, I want tool calls shown as short details under their step, so that I know what the agent is doing.
14. As a user, I want agent text to stream in with a caret, so that I can read as it is written.
15. As a user, I want the idea's stage shown as a label, so that I know where in the flow the idea is.
16. As a user, I want all of this to update without refreshing the page, so that the run feels live.
17. As a user who reloads or reopens the idea page, I want the idea, the latest run and every step so far restored, so that I lose nothing.
18. As a user whose connection drops, I want the stream to resume where it stopped with no duplicated or missing rows, so that the view stays true.
19. As a user opening a run that finished long ago, I want to see its final status rather than a spinner forever, so that the page settles.
20. As a user, I want the send button to become a stop button while a run is active, so that I can stop a run I no longer want.
21. As a user who pressed stop, I want "Stopping…" until the run actually stops, so that I know the request was taken.
22. As a user, I want a stopped run shown as cancelled, so that I know it ended on purpose.
23. As a user whose run failed, I want an inline error row with the reason, so that I understand what happened.
24. As a user whose run failed, I want a Retry button that starts a new run, so that I can try again without retyping.
25. As a user who retries while another run of the idea is still active, I want the "already running" message inline, so that I know why nothing started.
26. As a user whose run asks a question, I want to see the question text, so that I know the run is waiting for me (answering comes in SHIP-239).
27. As a user who opens the idea of another workspace or a deleted idea, I want a clear "not found" state, so that I do not see a broken page.
28. As a user whose session expires while watching, I want the usual "Signed out" toast and redirect, so that I can sign back in.
29. As a user whose run cannot start (for example no LLM key), I want the server's message inline near the composer, so that I know to open settings.
30. As a user, I want to find and reopen my past ideas, so that I can go back to one I submitted before (see Open questions).
31. As a phone user (375px), I want the thread and composer to fit with no horizontal scroll, so that I can use Metis on mobile.
32. As a screen-reader user, I want new steps and text announced politely, so that I follow progress without focus jumping.
33. As a keyboard user, I want the stop, send and retry buttons labelled with tooltips and reachable by Tab, so that I can use everything without a mouse.
34. As a user who prefers reduced motion, I want no shimmer or caret blink, so that the page is calm.
35. As a user, I want agent text rendered as safe markdown, so that formatting works and nothing in the text can run script.

## Requirements

1. **Compose and submit (`/`).** `EmptyChat` keeps its title, line and suggestion chips and gets a real `Composer` (`components/chat/`): auto-growing textarea (1 line → 180px), "Enter to send" hint, 26px send button; Enter sends, Shift+Enter is a new line; a chip fills the textarea. One Zod schema (`lib/schemas/`) validates the text: trimmed raw text 10–10,000 characters; the derived title must be 3–120 characters (title rule: see Open questions). On submit: `POST /v1/ideas {title, raw_text}` → `POST /v1/ideas/{id}/runs` with a fresh `Idempotency-Key` (UUID per submit attempt, reused on a network retry of the same attempt) → `router.push("/ideas/{id}")`. Send is disabled while pending. A failure shows `errorMessage(err)` inline under the composer; field errors map to the textarea. If the idea is created but the run start fails, still route to the idea page, which offers Start (same flow as Retry).
2. **Idea page (`/ideas/[ideaId]`).** Loads the idea (`GET /v1/ideas/{id}`) and the latest run (`GET /v1/ideas/{id}/runs?limit=1`, first item or none) through new query hooks (`useIdea`, `useLatestRun`, workspace-scoped keys). Renders `Thread` (`aria-live="polite"`) with `UserBubble` (the idea's `raw_text`, `whitespace-pre-wrap`) and one `AgentMessage` for the latest run, plus the `Composer` pinned at the bottom (in this PRD it only stops runs; typing is disabled with the placeholder "Answering comes soon" unless the run is awaiting a question — see 7). `404 idea.not_found` → a not-found state with a link to `/`. Loading → square skeleton lines, no spinner page.
3. **`useRunEvents(runId)` (`lib/events/`).** Opens `new EventSource("/v1/runs/{id}/events?workspace_id=<id>", {withCredentials: true})` (workspace id from `useWorkspaceId()`; no stream token, no headers). Listens for the six server event names; each frame's `data` is parsed with a Zod schema of the envelope `{run_id, type, data, ts}` and a per-type payload schema; a frame that fails parsing or has an unknown type is ignored. Valid events feed a pure reducer (`runReducer(state, event) → state`) that returns a new state each time. The browser resends `Last-Event-ID` on reconnect, so the hook never dedupes by itself beyond the reducer rules in 4. On a terminal `run_status` (`succeeded`, `failed`, `cancelled`) the hook closes the `EventSource` and stops reconnecting. Closing the page closes the source. An `event: error` frame (server-side malformed entry) closes the source and shows a generic inline error. The hook returns the reducer state and the connection state.
4. **Event → UI mapping** (server names, kept as is):

   | Event | Payload | Reducer / UI effect |
   | --- | --- | --- |
   | `run_status` | `{status, error?: {code, message}}` | Run status: composer busy (`queued`, `running`), stage label refetched, `failed` → error row with `error.message`, `cancelled` → "Run stopped" row, `awaiting_user` → stop streaming caret |
   | `node_started` | `{node}` | Add a step row for `node` (spinner); a `node_started` for a node whose latest row is still running is a no-op (a node may run twice, e.g. the stub interviewer and scorer) |
   | `node_finished` | `{node}` | Mark that node's latest running row done (check); no running row → add one done |
   | `tool_call` | `{node, name}` | Add `name` as a detail under that step |
   | `token` | `{node, text}` | Append `text` to the streamed text; caret while the run is `running` |
   | `interrupt` | `{type: "question", question}` or `{type: "approval", action, details}` | Show the question (or action) as a placeholder row |

   On page load the reducer starts from the run view: `status`, `error` and `pending_interrupt` seed the state, then the stream replays every event from the start, so steps and text are rebuilt from the stream (a replay of the full stream is the restore path; no step history is stored elsewhere).
5. **Stage label.** Shows the idea's `stage` (from the idea query; `run_status` events invalidate `useIdea` and `useLatestRun` so the label and run view follow).
6. **Cancel.** While the run is `queued`, `running` or `awaiting_user`, the send button becomes a stop button (`aria-label="Stop"`, tooltip). Stop → `POST /v1/runs/{id}/cancel`. Result `cancelled` → done at once (the server also publishes `run_status: cancelled`). Result `running` → show "Stopping…" and keep the stop button disabled until `run_status: cancelled` (or another terminal status) arrives.
7. **Awaiting user.** `interrupt` events and `pending_interrupt` on the run view render a placeholder row with the question text (or the approval action) and the note that answering is coming. No resume call (SHIP-239).
8. **Failure and Retry.** `run_status: failed` → inline error row (destructive text, `error.message`, `error.code` in mono) with Retry. Retry → `POST /v1/ideas/{id}/runs` with a new `Idempotency-Key` → the page switches to the new run (invalidate `useLatestRun`, the hook reopens on the new run id). `409 run.already_running` → inline "A run is already in progress for this idea." The same Start button appears when the idea has no run.
9. **Agent text.** Streamed text renders with `react-markdown` + `remark-gfm`, no raw HTML, links `rel="noopener noreferrer"`. Per the ui-context rule, agent text is untrusted.
10. **Components** (`components/chat/`): `Thread`, `UserBubble`, `AgentMessage` (22px mark + "Metis"), `StepList` (bordered box, spinner → check), `Shimmer` (current step label, none under `prefers-reduced-motion`), `Composer` (shared by `/` and the idea page), `RunErrorRow`, `InterruptPlaceholder`. Styles per `ui-context.md` and the chat sample, tokens only, square, light and dark.
11. **Hooks.** Queries: `useIdea(id)`, `useLatestRun(ideaId)` (+ the ideas list hook if Open question 1 is answered that way). Mutations: `useCreateIdea`, `useStartRun`, `useCancelRun`. All on the generated client; no hand-written API types.
12. **Past ideas.** `RecentIdeas` popover in `AppHeader` (icon button with `aria-label` + tooltip): `useIdeas()` over `GET /v1/ideas`, items show title and stage and link to `/ideas/{id}`, "Load more" follows `next_cursor`, square skeleton while loading, "No ideas yet" when empty.
13. **Docs sync.** `ui-context.md`: replace the Live Run Events table with the server event names and payloads above (drop `step.progress`, `research.item`, `score.*` until the server emits them; keep a note that they come later), describe `useRunEvents` (`?workspace_id=`, closes on terminal status, ignores unknown events), document the title rule, the past-ideas entry point and which composer tools ship.

## Out of scope

- Answering questions or approvals (`POST /v1/runs/{id}/resume`), research panel, sources, score card: SHIP-239 and later.
- Composer tools with no server feature: attach, web research toggle, mention a past idea, model picker (see Open questions).
- Agent message actions (copy, regenerate, thumbs up).
- Editing or archiving an idea from the web.
- Showing runs other than the latest one, or a run history.
- Any server change.

## Touches

- `web/app/(app)/page.tsx`, `web/app/(app)/ideas/[ideaId]/**`
- `web/components/chat/**` (and `components/frame/app-header.tsx` only if the past-ideas entry lives in the header)
- `web/lib/events/**` (new: `use-run-events.ts`, event schemas, reducer)
- `web/lib/api/queries/`, `web/lib/api/mutations/`, `web/lib/schemas/`
- `web/e2e/` (new spec + support)
- `.agents/ctx/ui-context.md` (Live Run Events, title rule, past ideas, composer tools)
- `.agents/progress-tracker.md`

## Dependencies

- `feat-web-sign-in` (SHIP-221), `feat-web-api-client` (SHIP-222), `feat-web-shell-settings` (SHIP-224): done (SHIP-219).
- `feat-run-graph-job` (SHIP-228), `feat-runs-api` (SHIP-232), `feat-run-events-sse` (SHIP-234): done (SHIP-225).
- `feat-auth-sessions` / `feat-auth-google` / `refactor-remove-jwt-auth` / `refactor-auth-module`: done (SHIP-263).
- `feat-ideas-crud` (SHIP-218): done.

## Testing

Two seams, both already in the repo (proposed; confirm in Open questions):

1. **Browser seam (primary):** Playwright on the compose stack (SHIP-221's harness: seeded user + session cookie). Drives the UI and checks server state through the API. Real runs execute on the worker with stub specialists.
   - Submit an idea from `/` → lands on `/ideas/{id}`, user bubble shows the text, step rows appear and turn to checks without a reload, run ends `succeeded`.
   - Reload mid-run and after the run → same steps, no duplicate rows (count rows against the distinct `node_started` nodes).
   - Cancel → "Stopping…" or cancelled, `GET /v1/runs/{id}` is `cancelled`.
   - Failed run, interrupt placeholder, malformed and unknown frames: `page.route` on `/v1/runs/*/events` fulfils a hand-written `text/event-stream` body (the stubs never fail or ask on their own). Retry starts a new run (`GET /v1/ideas/{id}/runs` has two); a second concurrent start shows the 409 message.
   - Validation: short text blocked client side, no request sent.
   - Unknown idea id → not-found state.
   - Visual: `/` and an idea page at 1280px and 375px, light and dark, against the chat sample; no horizontal scroll; thread has `aria-live="polite"`.
2. **Pure-function seam:** Vitest on `lib/events/` (reducer and event schemas) and `lib/schemas/` (idea form and title rule), like the existing `lib/` tests. Reducer tests feed event sequences and assert the resulting state: replay order, idempotent repeated `node_started`, terminal states, unknown events ignored, state never mutated.

No component unit tests. `npm run lint`, `typecheck`, `build` pass.

## Acceptance criteria

- [x] Sending an idea shows live step progress without a refresh.
- [x] Closing and reopening the page resumes the event feed with no duplicate rows.
- [x] Cancel stops the run; a failed run shows its error and Retry.
- [x] An awaiting run shows its question text as a placeholder.
- [x] Every SSE payload and the idea form are validated with Zod; agent text is sanitized markdown.
- [x] Light and dark match the chat sample; works at 375px; thread is `aria-live="polite"`.
- [x] `ui-context.md` Live Run Events uses the server event names.
- [x] `npm run lint`, `typecheck`, `build` pass; Vitest and Playwright specs above pass.

## Open questions

None open.

## Resolved (user, 2026-11-18)

1. Past ideas: a recent-ideas popover in the app header (`GET /v1/ideas`, newest first, cursor "Load more"; each item links to `/ideas/{id}` with title and stage; empty state "No ideas yet"), documented in `ui-context.md`. Adds `useIdeas()` (infinite query) and touches `components/frame/app-header.tsx`.
2. Title: derived from the first non-empty line of the text, trimmed to 120 characters; at least 3 characters, else the form error asks for a longer first line. No title field.
3. Composer tools (attach, web research, mention, model): left out; `ui-context.md` notes they come with their server features.
4. Test seams: Playwright on the compose stack (real stub runs; `page.route` fakes failed / interrupt / malformed streams) plus Vitest on `lib/events/` and `lib/schemas/`.

Built (2026-11-18):

- Composer placeholder on the idea page is "Answering comes soon" (textarea disabled until SHIP-239).
- The stream refetches the idea and run only when it ends (terminal status, server `error` frame, or the browser giving up), not on every replayed `run_status`. A lost feed shows "Live updates stopped. Reload the page to see the latest progress." and stops the spinners; the refetch also sends an expired session to sign-in.
- If the idea is created but its first run does not start, `/` still opens the idea and shows the reason in a toast (the page changes under the reader).
- Stop reads "Stopping…" only when cancel answers `running`.
- The run view is keyed by workspace and run id, so a reopened stream always replays into a fresh state.
- Added beyond the spec, small: "Run finished." note, follow-to-bottom scrolling, a generic "Could not load this idea" state.
- Not covered by Playwright: "Stopping…" (stub runs finish before a click lands; a queued run cancels at once). Checked by reading the cancel route.
- Server gap found: nothing writes the graph's stage back to `ideas.stage`, so the stage badge stays "Intake" for stub runs. Out of scope (no server changes); needs a server issue.
- Fixed a flaky selector in `e2e/shell-settings.spec.ts` (workspace submenu matched only its loading label).

Notes from the issue (not questions): the issue's "`detail`" on a failed run is `error.message` (the server publishes `error: {code, message}`); a finished run with an expired stream gets one synthetic `run_status` frame (SHIP-234), which the reducer handles like any terminal status.

## Status

done
