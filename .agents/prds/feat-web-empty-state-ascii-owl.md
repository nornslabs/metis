# PRD: feat-web-empty-state-ascii-owl

Linear: SHIP-293 · https://linear.app/heimdallabs/issue/SHIP-293/428-empty-state-ascii-owl-background-and-motion-polish

Milestone: M5 — Spec and planning. Parent: SHIP-285 (42 · Web workspace redesign), sub-issue 42.8. Blocked by SHIP-288 (`feat-web-chat-dock`, done) and SHIP-289 (`feat-web-history-panel`, done). Web only.

## Problem / Goal

The new workspace is built but the first and last impressions are rough. `/` shows a bare title and suggestions with no way back into past ideas, the conversation has no ASCII owl behind it, and motion is only partly consistent with the Motion table in `ui-context.md`.

Goal: finish the workspace's look. A useful empty state on `/` (faint owl, title, one line, a "Pick up where you left off" box with the two most recent ideas), the faint `AsciiOwl` behind the chat that closes its eyes while Metis works, one consistent motion pass that is off under `prefers-reduced-motion`, and a final side-by-side check against `design/samples/metis-workspace-shadcn.html` in light and dark.

## User stories

1. As a returning user, I want to see my two most recent ideas on the empty screen, so that I can pick up where I left off in one click.
2. As a returning user, I want each recent idea to show its title, stage · time, score trend and latest score, so that I can tell which one I want without opening it.
3. As a returning user, I want a click on a recent idea to open that idea's conversation, so that I land in the right place.
4. As a returning user, I want an "All ideas" link that opens the history panel, so that I can find an older idea.
5. As a first-time user with no ideas, I want no empty "recent" box, so that the screen stays clean and points only at the composer.
6. As a user, I want a faint outlined owl above the title, so that the first screen has the product's character.
7. As a user on a short screen (under 640px tall), I want the owl hidden, so that the title, recent box and composer all fit.
8. As a user, I want the suggestions to sit just above the composer, so that one click fills my idea.
9. As a user in a conversation, I want a faint ASCII owl behind the thread, so that the chat has a quiet background that matches the brand.
10. As a user, I want the ASCII owl never to block clicks or text selection, so that it is decoration only.
11. As a user, I want messages to stay readable over the owl in light and dark, so that decoration never costs legibility.
12. As a user, I want the ASCII owl to fade in over 0.6s when a conversation opens, so that it does not flash in.
13. As a user, I want the ASCII owl to close its eyes briefly every 2.6s while Metis is working, so that I can tell it is busy without reading anything.
14. As a user, I want the owl's eyes to stay open when Metis is idle, waiting for me or finished, so that blinking means working.
15. As a user on a phone, I want the ASCII owl smaller (6px type), so that it fits the narrow chat.
16. As a user who prefers reduced motion, I want no fade, no blinking and no slide or bar animation, so that the product does not move.
17. As a screen-reader user, I want the ASCII owl hidden from assistive technology, so that I do not hear a block of punctuation.
18. As a keyboard user, I want the recent ideas to be links reachable by Tab with a visible focus ring, so that the empty state works without a mouse.
19. As a user, I want messages to come in with a 250ms fade and a 6px rise, so that new text arrives gently.
20. As a user, I want the side panels to slide in 250ms and the score bars to grow over 800ms, so that motion is consistent across the app.
21. As a user, I want hover and colour changes to take 120–150ms, so that controls feel responsive and uniform.
22. As a reviewer, I want the finished screens checked against the sample in light and dark at 1920, 1440 and 375px, so that the redesign (SHIP-285) can close.
23. As a developer, I want the ASCII conversion to be a pure function, so that it can be tested without a canvas.

## Requirements

1. **`EmptyState`** (`components/chat/empty-state.tsx`, client). The hero on `/`. Content, top to bottom: faint outlined owl (76px, `muted-foreground`, outline stroke `0.35`, pupils kept; hidden under 640px viewport height), title "What are you building?", the existing one-line description, then the recent box. Styles follow the sample's `.hero-owl`, `.recent`, `.rc-*` rules with theme tokens only (no hex, no radius). `EmptyChat` keeps the form, submit and key gate and renders `EmptyState` in place of its current title block; the suggestions stay above the composer (already so; unchanged).
2. **Recent box** (`components/chat/recent-ideas.tsx`). Header "Pick up where you left off" and an "All ideas" button that opens the history panel (`openHistory` from the workspace panels). Two rows from the first page of `useIdeas()` (latest activity first), scores from `useScoreSummaries` for those two ids; the row data is `toHistoryRow` (`lib/history/rows.ts`). Row: title (one line, truncated), `stage · time` (`stageLabel`, `relativeTime`), `ScoreSpark`, a band square and the latest score (`–` when unscored), then an arrow icon. Each row is a `next/link` to `/ideas/{id}`. `aria-label` follows `IdeaRow`'s wording. The box is not rendered while the list is loading, empty or failed (no skeleton, no error text: the empty state must work with no history). Archived ideas are not shown (the list already hides them).
3. **`AsciiOwl`** (`components/chat/ascii-owl.tsx`, client, `aria-hidden`, `pointer-events-none`). Rasterises the owl path once on the client into a 72×46 character grid with the ramp ` .,:;-=+*#%@` and renders it in a `pre` behind the thread. The raster reproduces the sample's drawing (face gradient, feather chevrons, eye rings, pupils; second frame with closed eyes). Type: Geist Mono 9px / 9px line height (6px under 820px), `foreground` at 7.5% opacity (9% in dark), centred above the dock (bottom padding that clears the dock). Frames are computed once (module cache) after mount: server render and first client render are an empty `pre`, so there is no hydration mismatch. If a canvas 2D context is unavailable, nothing is rendered and the page works.
4. **Pure conversion** (`lib/chat/ascii-owl.ts`). `rampChar(luma)` and `gridFromLuma(...)` map a luma buffer (width, height, cell size) to rows of characters with trailing spaces trimmed, exactly as the sample's loop does (sampling every second pixel inside a cell). No DOM access, no mutation of inputs.
5. **Mounting and visibility.** The `AsciiOwl` layer is mounted by the conversation layout (`/ideas/[ideaId]`), absolutely positioned behind the scrolling thread inside the chat pane; the thread and dock sit above it. It is not rendered on `/` (that page is not chatting). It fades in over 0.6s on mount. The scroll area background stays transparent so the owl shows through.
6. **Working eyes.** While the latest agent message's owl state is `working` (the same state that animates `OwlMark` and `WorkingBar`), the closed-eyes frame shows for 160ms every 2.6s. In any other state the open-eyes frame stays. Timers are cleared on unmount and when the state changes. Under `prefers-reduced-motion: reduce` there is no fade and no blink (open frame only).
7. **Motion pass.** One audit of the Motion table against what is built, fixing gaps only (no restyle):
   - message in: 250ms fade + 6px rise (`UserBubble`, `AgentMessage`, run rows that appear in the thread);
   - panel width and slide: 250ms `cubic-bezier(.2,.7,.2,1)` (history panel, output panel);
   - score bars: 800ms width on the same curve;
   - hover and colour: 120–150ms on buttons, rows, links and toggles built in this redesign (recent rows, history rows, edge toggles, pane tabs, suggestion buttons);
   - popover in: 140ms fade + 4px rise where a custom popover exists (shadcn components are not edited).
   Durations come from named tokens or utilities in `globals.css`, not scattered literals. Every animation and transition is removed under `prefers-reduced-motion: reduce`; a test or the audit lists what was changed.
8. **Final visual check.** Compare `/` and an idea conversation (chat only, then with each panel open) with `design/samples/metis-workspace-shadcn.html`, light and dark, at 1920, 1440 and 375px. Differences are fixed inside this PRD's scope; anything else becomes an Open question in the tracker. See Open questions for how the check is run.
9. **Docs.** Update `ui-context.md` (`EmptyState`, `AsciiOwl`, Motion table, route table row for `/`, file tree) to match what is built, including the empty-state source (`useIdeas` + `useScoreSummaries`) and the "box hidden with no ideas" rule.
10. **Tests.** Written with the code; CI runs them.

## Decisions taken while building

- Motion audit (requirement 7). Changed: message in 150ms → 250ms (`UserBubble`, `AgentMessage`: `duration-250`); score bars `ease-out` → `ease-panel`. Already matching, left as is: history and output panel width (`duration-250 ease-panel`), edge toggle (`duration-150`), history rows and the new recent rows (`transition-colors`, 150ms), popovers (shadcn, not edited). Everything new uses `motion-safe:` or `motion-reduce:`; the ASCII owl layer has no fade and no blink under reduced motion (the e2e checks `animation-name: none` and open eyes). Duration utilities are the existing Tailwind ones (`duration-150/250/600/800`, `ease-panel`); no new motion token was needed.
- New files outside the first Touches list: `lib/chat/ascii-owl-frames.ts` (canvas drawing), `lib/use-reduced-motion.ts`, `lib/brand/owl-path.ts` (one owl path for `OwlMark`, the hero and the ASCII owl), `components/history/band-square.ts` (shared with `IdeaRow`), `rowLabel` moved to `lib/history/rows.ts`, `lib/cn.ts` (new `ascii` size and tracking names), `app/globals.css` (`text-ascii`, `tracking-ascii`, `short` variant).
- The hero owl hides at 640px tall or less (`max-height: 640px`).
- Frames come from `useSyncExternalStore` (server snapshot null), not an effect, so the server and first client render match.
- Visual check (requirement 8, user decision): ran a dev server on the compose stack's API and looked in Chrome at `/` (dark, 1440; light and dark at the browser's 500px minimum width) and an idea conversation (dark and light at 1440; 500px). The ASCII owl is faint and readable behind messages in both themes, 6px type at narrow widths, no horizontal scroll. The window cannot go under 500px wide or over the screen, so 375px and 1920px were not seen exactly; the side panels open over the chat were not compared.
- Dev-only Next errors ("unstable value `Math.random()`" from `lib/auth/get-me.ts` on every route) appear in the dev overlay; they are not from this change.
- Code review (Standards and Spec) found no hard violations; fixed: owl path copied three times, `rowLabel` copied, terse timer names, a "just now" assertion that could not hold, a brittle hero-owl selector, PRD Touches and audit record. Not changed (judgement): `ASCII_GRID` constant, keying frames by `"open" | "shut"`, shared `useReducedMotion` for older CSS-only spots, the fixed wait in the reduced-motion e2e (a negative check).
- Tests not run locally; CI runs them.

## Out of scope

- Any server change (the list and score-summary routes already exist).
- A new "recent ideas" API, pagination in the empty state, or a count other than two.
- Showing the ASCII owl on `/` or behind the output or history panels.
- A different owl drawing, other colours, or a settings toggle for the background.
- Restyling shadcn components in `components/ui/*`; changes to the sign-in page.
- New screens or behaviours not in `ui-context.md` or the samples.

## Touches

- `web/app/(app)/page.tsx`
- `web/components/chat/` (`empty-chat.tsx`, `empty-state.tsx`, `recent-ideas.tsx`, `ascii-owl.tsx`, `conversation-layout.tsx`, `user-bubble.tsx`, `agent-message.tsx`)
- `web/lib/chat/ascii-owl.ts`
- `web/app/globals.css` (motion tokens and the ASCII owl utilities)
- Motion fixes in `components/history/`, `components/panel/`, `components/score/`, `components/chat/edge-toggle.tsx` only where the audit finds a gap
- `web/e2e/` (new spec), Vitest files beside the code
- `.agents/ctx/ui-context.md`

## Dependencies

SHIP-288 (`feat-web-chat-dock`, done: thread, dock, owl state), SHIP-289 (`feat-web-history-panel`, done: `IdeaRow` data, `ScoreSpark`, `useScoreSummaries`, panel open action). Also relies on SHIP-286/287 (done: `OwlMark`, workspace layout). Last sub-issue of SHIP-285.

## Acceptance criteria

1. `/` shows the faint owl, title, one line and, when the workspace has ideas, the "Pick up where you left off" box with the two most recent ideas (title, stage · time, `ScoreSpark`, score, arrow) and an "All ideas" link that opens history. With no ideas the box is absent.
2. Clicking a recent idea opens that idea's conversation; the link goes to `/ideas/{id}`.
3. The owl is hidden under 640px viewport height; suggestions sit above the composer.
4. On an idea page the ASCII owl is visible behind the thread, fades in over 0.6s, is `aria-hidden`, never blocks clicks or text selection, and messages stay readable over it in light and dark.
5. While a run is working the owl's eyes close for 160ms every 2.6s; when it is idle, waiting or finished they stay open.
6. Under `prefers-reduced-motion: reduce` nothing fades, blinks, slides or grows.
7. Message in, panel slide, score bars and hover timings match the Motion table.
8. The screens match the sample in light and dark at 1920, 1440 and 375px (see Open questions).
9. `npm run lint`, `npm run typecheck` and `npm run build` pass; tests are written and left for CI.
10. `ui-context.md` matches the built result.

## Testing

Seam: the web app as a user sees it, at Playwright (the `spec-pane.spec.ts` / `research-pane.spec.ts` pattern: `page.route` fakes for the ideas list, score summaries, the idea and the event stream), plus Vitest for the one pure function. New spec `empty-state.spec.ts`. A good test checks what the user sees and does, not component internals. Not tested at pixel level (the visual check is manual).

- Empty state with ideas: two rows in latest-activity order with title, `stage · time`, score; a third idea is not shown; clicking a row navigates to `/ideas/{id}`; "All ideas" opens the history panel.
- Empty state with none, or a failed list: no box, composer still works.
- Short viewport (height 600): the hero owl is not visible.
- ASCII owl on an idea page: present, `aria-hidden`, `pointer-events: none`, text in the thread is selectable and clickable through the layer; absent on `/`.
- Eyes: with a fake stream that keeps a step running, the `pre` text alternates to the closed-eyes frame (compare to the open frame); with the run finished it stays on the open frame; with `reducedMotion: "reduce"` it never changes.
- Reduced motion: the owl layer has no transition and `animate-*` classes resolve to no animation (computed style).

Vitest: `lib/chat/ascii-owl.ts` (ramp ends map to space and `@`, row trimming, grid size, a tiny hand-made luma buffer gives the expected rows, inputs not mutated). Tests are not run locally; CI runs them.

## Open questions

None.

Resolved (user decision, 2026-11-23, recommended): the final visual check runs during `/implement-spec` with `docker compose up` and the Chrome tools, at 1920, 1440 and 375px in light and dark. The same pass also looks at the SHIP-288 to 292 screens (never visually checked); differences inside this PRD's scope are fixed, the rest go to the tracker's Open Questions.

## Status

done
