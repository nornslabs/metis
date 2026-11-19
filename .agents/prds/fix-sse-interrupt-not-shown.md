# PRD: fix-sse-interrupt-not-shown

Linear: SHIP-271 · https://linear.app/heimdallabs/issue/SHIP-271/fix-live-interview-question-never-shows-sse-buffered-by-next-gzip

## Problem / Goal

On a live run the interview question never appears and the composer stays blocked ("Metis is working…", "searching"). A fresh page load shows the question and the composer correctly.

Root cause (verified in the browser): the Next.js server compresses the proxied `/v1/runs/{id}/events` response (`content-encoding: gzip`) and buffers it, so no SSE frame reaches the page. The same stream read directly from the API delivers frames at once. The server side is correct: the worker saved the question, set `awaiting_user` and published `interrupt` + `run_status`.

Two smaller problems found on the way:

- The page calls `GET /v1/ideas/{id}/research` on every load, before research can exist, so devtools shows a red `404 research.not_found` row (handled as empty, but noisy).
- The page learns that a run paused only through the stream. If the stream is silent for any reason, nothing recovers.

## User stories

1. As a user, I want the question Metis asks to appear as soon as the run pauses, with the composer enabled, so that I can answer it.
2. As a user, I want the page to recover when the live stream is silent, so that a run waiting for me never looks stuck.
3. As a developer, I want no `404` research request before the Researcher has started, so that devtools shows real errors only.

## Requirements

1. Disable response compression in `web/next.config.ts` (`compress: false`), with a comment saying why (SSE through the `/v1` rewrite).
2. `runReducer` accepts a `sync` action built from a run view (`status`, `error`, `pending_interrupt`). It only changes state when the view differs from it: a different status, or a pending interrupt the page has not seen (then `interruptCount` + 1). It never moves a terminal state back.
3. `useRunEvents` exposes `sync(view)`. `RunConversation` polls `GET /v1/runs/{id}` every 5 s while the run is `queued` or `running` and calls `sync` with the result. The poll is a safety net: the stream stays the primary source.
4. `useResearch(ideaId, { enabled })` runs only when `enabled`. `ResearchSection` passes `researchStarted`. The 404-to-`null` handling stays as a backstop.

## Out of scope

- Replacing SSE with WebSocket.
- Any server change.
- Polling for steps or tokens (only status and the pending interrupt).

## Touches

- `web/next.config.ts`
- `web/lib/events/` (reducer, `use-run-events`)
- `web/lib/api/queries/` (`use-research`, new `use-run`)
- `web/components/chat/run-conversation.tsx`, `web/components/research/research-section.tsx`

## Dependencies

- feat-web-interview-research (done)
- feat-run-events-sse (done)

## Acceptance criteria

1. In the browser, the `events` request through `:3000` delivers frames as the run emits them (no `content-encoding: gzip`).
2. Starting a new idea shows the first interview question and an enabled composer without a reload.
3. With the stream blocked, the question and composer still appear within about 5 s.
4. No `research` request is sent before a Researcher step starts.
5. `npm run lint`, `npm run typecheck`, `npm run build` and the unit tests pass.

## Open questions

None.

## Status

done
