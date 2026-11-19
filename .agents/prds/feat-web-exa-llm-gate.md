# PRD: feat-web-exa-llm-gate

Linear: SHIP-273 · https://linear.app/heimdallabs/issue/SHIP-273/web-exa-warning-llm-key-gate-and-research-skipped-notice

Milestone: M3 — Interview and discovery. Branch: `feat/web-exa-llm-gate`. Web only.

## Problem / Goal

The server (SHIP-272, merged) now refuses to start a run unless the workspace has an LLM key whose last test passed (`402 provider.llm_not_ready`), and it skips research, with a `notice` run event, when no Exa key is saved. The web knows neither rule: it lets the user type an idea and press Send, then shows a raw error or a toast; and a skipped research looks like an unexplained gap in the steps (the `notice` event is ignored as unknown).

Goal: the user learns before starting what will and will not happen, cannot start a run that is certain to be refused, and sees an explicit note in the run when research was skipped.

## User stories

1. As a user with no LLM key, I want the composer and Start blocked with a clear line and a link to Settings, so that I do not write an idea that cannot run.
2. As a user whose LLM key was never tested, I want to be told to test it, so that I know what to do next.
3. As a user whose LLM key failed its last test, I want to be told it failed, so that I fix or replace it.
4. As a user with no Exa key, I want one banner before Start saying Metis will interview but skip research, so that I am not surprised after the interview.
5. As a user, I want the banner's link to open Settings on the API keys tab, so that I can add the key in one click.
6. As a user who just tested or saved a key in the settings sheet, I want the block and banner to disappear without a reload, so that I can carry on at once.
7. As a user with both keys ready, I want no banner and no block, so that nothing gets in my way.
8. As a user on an idea with no run yet, I want Start blocked under the same rules, so that the rule is the same everywhere.
9. As a user whose run failed, I want Retry blocked under the same rules, so that a retry does not bounce.
10. As a user whose key stopped working between page load and Start, I want a clear message with a Settings link instead of a generic error, so that I know why (the server's `402` is the backstop).
11. As a user whose idea was saved but whose first run was refused, I want to land on the idea page with the reason and the Settings link, so that I can fix it and press Start.
12. As a user whose run skipped research, I want a note in the run saying so, so that the missing research is explained.
13. As a user, I want that note to offer a link to add the Exa key, so that a new run can include research.
14. As a user who reloads after a skipped run, I want the note shown again, so that the page matches what happened.
15. As a user, I want the skipped run to read as finished, not failed, so that I do not think something broke.
16. As a screen-reader user, I want the banner and the note announced politely and the blocked controls explained, so that I understand why they are disabled.
17. As a keyboard user, I want the Settings link reachable in the tab order before the composer, so that I can fix the key without a mouse.
18. As a phone user (375px), I want the banner to wrap with no horizontal scroll, so that I can read it.
19. As a user in light or dark theme, I want the banner and the note to match the rest of the UI, so that nothing looks out of place.
20. As a workspace member who cannot edit keys, I want the same line and link, so that I can see why I am blocked (Settings shows the keys read-only and lets me Test).

## Requirements

1. **Key readiness (pure).** `lib/keys/readiness.ts` derives from the `GET /v1/settings` view (`ProviderKeys`, already typed): `llm` is `ready`, or blocked with reason `not_configured` (no `llm` key), `not_tested` (`last_test_ok` is `null`) or `test_failed` (`false`), the same reasons as the server's `meta.reason`; `exa` is `present` or `missing`. One function, unit tested.
2. **Gate hook.** `useKeyGate()` over `useSettings()` returns the readiness once loaded. While loading, and when settings fail to load, it blocks nothing and shows no banner (the server's `402` is the backstop); it never shows a stale "ready" for another workspace (the query key already includes the workspace id).
3. **LLM block.** When the LLM key is not ready, the composer on `/` is read-only with its send button disabled, and Start (idea with no run) and Retry (failed run) are disabled. A single line, in the same place as the banner, says why per reason ("Add an LLM key to start.", "Test your LLM key to start.", "Your LLM key failed its last test.") with a link "Open API keys" to `?settings=keys` (a plain `<Link>`: `useOpenSettings` reads `useSearchParams`, which stops `/` from prerendering). The blocked control carries `aria-describedby` pointing at the line.
4. **Exa banner.** Above the composer on `/` and on an idea with no run, when the LLM key is ready and no Exa key is saved: "Metis will interview you but skip research: Exa isn't set up. Add a key in Settings to include it." with the same link. It is not shown on a run in progress. Not dismissible (it disappears when the key is added).
5. **Live update.** Saving, testing or removing a key in the settings sheet already invalidates the settings query; the gate and banner follow it. Verify, and add the invalidation if any key mutation misses it.
6. **Start `402`.** `provider.llm_not_ready` from the start call (the idea page's Start / Retry, and the `/` submit) is mapped to the same reason text as requirement 3 (from `meta.reason`; unknown reason → the server's `detail`), with the Settings link; it also refetches settings so the gate catches up. On `/`, the idea was created before the run was refused: go to the idea page as today, and show the reason in the existing toast with an "Open API keys" action.
7. **`notice` event.** Add `notice` to `RUN_EVENT_TYPES` and the Zod schemas (`{code, text}`), and to the reducer as `notices: readonly {code, text}[]` in `RunState` (a repeated code is kept once; the stream replays from the start on reload, so a reload shows it again). Unknown codes show their `text`.
8. **Notice row.** In the agent message, under the step list, a quiet bordered row with an info icon and the notice `text` (plain text, never markdown). For `research.skipped_no_exa` it also carries the "Open API keys" link ("Add a key in Settings to include research in a new run"). It is not an error row: no destructive color.
9. **Skipped step.** `RunStep` gains a `skipped` state (user decision). A `notice` with code `research.skipped_no_exa` marks the Researcher's latest step skipped (a small code-to-node map in `lib/events/`; other codes touch no step), and a skipped step shows a distinct mark (no spinner, no check) and "(skipped)" after the node name in the step list. The skip path may send no `node_finished`, so a step still running when the run `succeeded` also closes (a `failed` or `cancelled` run keeps its running step visible). The run still ends "Run finished." Fix the reducer and step list, not the server.
10. **Components.** `components/chat/`: `KeyGateNotice` (the one line and the banner, one component, `role="status"`), `RunNotices` (the notice rows). Tokens only, square, 1px line, `--warning` for the banner icon, light and dark per the samples; no new custom lengths unless needed (then in `globals.css` and `lib/cn.ts`).
11. **Docs sync.** `ui-context.md`: components (`KeyGateNotice`, `RunNotices`), Live Run Events (`notice`), Ideas (Start/Retry blocked, `402` mapping), Routes (`/` banner), and the "not emitted yet" line. `project-overview.md` only if its Exa wording is stale.
12. **Tests.** Vitest: readiness (all reasons, exa present/missing), `notice` parse (valid, malformed ignored), reducer (notice kept once, replay, steps closed at terminal status), 402 message mapping. Playwright with `page.route` fakes for `GET /v1/settings` and the start call: no LLM key blocks Send and shows the line with the link; untested and failed variants; Exa missing shows the banner and ready+Exa shows none; testing a key in the sheet lifts the block; `402` on Start shows the mapped message; a stream with a `notice` shows the row and a skipped step, also after reload.

## Out of scope

- Any server change (done in SHIP-272), including running the key test automatically at start.
- Changing the settings sheet UI; only its existing query invalidation is relied on.
- A dismiss control or "don't show again" for the Exa banner.
- Role-specific copy for non-owners (the link and Settings' read-only view are enough).
- The score card and later stages.

## Touches

- `web/components/chat/` (`step-list.tsx`, `empty-chat.tsx`, `run-conversation.tsx`, `run-notice.tsx`, `use-run-actions.ts`, `agent-message.tsx` / `run-message.tsx`, new `key-gate-notice.tsx`, `run-notices.tsx`)
- `web/lib/events/` (`schemas.ts`, `reducer.ts`, `activity.ts`, tests)
- `web/lib/keys/` (new), `web/lib/api/queries/` (`use-key-gate`), `web/lib/api/errors.ts` (mapping, if shared)
- `web/e2e/`, `.agents/ctx/ui-context.md`

## Dependencies

- feat-optional-exa-llm-gate (done)
- feat-web-ideas-runs (done)
- feat-web-shell-settings (done)

## Acceptance criteria

1. With no LLM key, an untested key or a failed key, `/` cannot submit and an idea's Start / Retry is disabled; the line names the reason and its link opens the keys tab.
2. With a passing LLM key and no Exa key, one banner shows on `/` and on an idea with no run; with both keys, none.
3. Testing or saving a key in the sheet updates the block and banner without a reload.
4. A `402 provider.llm_not_ready` from a start call shows the mapped reason with the Settings link (toast on `/`, inline on the idea page).
5. A run whose stream carries `notice` shows the notice row (live and after reload), the step list has no spinner once the run ends, and the run reads "Run finished.".
6. Light and dark match the samples and `ui-context.md`; no horizontal scroll at 375px.
7. `npm run lint`, `npm run typecheck`, `npm run build`, Vitest and Playwright pass.

## Open questions

None. Decided with the user (2026-11-19): bordered row above the composer for the banner and the block line; fail open while settings load or fail; a distinct `skipped` step state.

## Status

done
