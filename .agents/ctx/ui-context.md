# UI Context

The Metis web app (`web/`). UI only: it talks to the server API and nothing else (no LLM, DB, Exa or MCP calls). Read with `project-overview.md`, `architecture.md` and `code-standards.md`.

Reference designs (source of truth for look and behavior):

- `design/samples/metis-chat-shadcn.html`: app shell, idea chat, account menu, settings sheet
- `design/samples/metis-auth-shadcn.html`: sign-in page

Open them in a browser before building a screen. Match them; do not restyle.

## Stack

| Concern       | Choice                                                                                  | Notes                                                                   |
| ------------- | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Framework     | Next.js App Router, React Server Components, TypeScript `strict`                        | Server Components by default; `"use client"` only for interactivity     |
| Styling       | Tailwind CSS v4 (CSS-first `@theme`), `tw-animate-css`                                  | Tokens only, no hex or arbitrary colors                                 |
| Components    | shadcn/ui (`base-nova` style, `base-color: neutral`, `radius: 0`), Base UI primitives   | Generated into `components/ui/` (protected)                             |
| AI components | shadcn.io chat parts: Message, Bubble, Prompt Input, Suggestion, Shimmer, Task, Sources | Pro blocks may be unavailable: build the same API in `components/chat/` |
| Icons         | `lucide-react`, 15px in controls, stroke 2                                              | Icon-only buttons always have `aria-label` + tooltip                    |
| Fonts         | Geist Sans + Geist Mono via `next/font` (`geist` package)                               | Mono for keys, URLs, kbd, eyebrows                                      |
| Theme         | `next-themes` (`attribute="class"`, light / dark / system)                              | Default `system`                                                        |
| Forms         | `react-hook-form` + `zod` (`@hookform/resolvers/zod`)                                   | One Zod schema per form, shared with server actions if any              |
| Server data   | TanStack Query v5                                                                       | One hook per resource in `lib/api/queries/`                             |
| API client    | `openapi-typescript` types + `openapi-fetch`                                            | Generated from the server OpenAPI; never hand-write API types           |
| Live events   | `EventSource` wrapped in `useRunEvents(runId)`                                          | Cookie auth, `Last-Event-ID` resume                                     |
| Toasts        | shadcn `sonner`                                                                         | Bottom center, square                                                   |
| Markdown      | `react-markdown` + `remark-gfm`, sanitized                                              | Agent text is untrusted                                                 |

## Folder Structure

```text
web/
├── app/
│   ├── layout.tsx                 # html/body, fonts, ThemeProvider, QueryProvider, Toaster
│   ├── globals.css                # Tailwind import, @theme tokens, light/dark variables
│   ├── (auth)/sign-in/page.tsx    # sign-in page (public)
│   ├── (app)/layout.tsx           # AppFrame: rails, safe area, header, footer; redirects to /sign-in when signed out
│   ├── (app)/page.tsx             # new idea: empty chat state
│   └── (app)/ideas/[ideaId]/page.tsx  # idea conversation for the latest run
├── components/
│   ├── ui/                        # shadcn/ui generated (do not edit)
│   ├── frame/                     # AppFrame, SideRails, GridGuides, CrossTick, AppHeader, RecentIdeas
│   ├── chat/                      # Thread, UserBubble, AgentMessage, StepList, AgentText, Composer, KeyGateNotice, QuickReplies, ApprovalPrompt, InterviewMessages, Shimmer, RunNotices, run notices, EmptyChat, IdeaConversation, RunConversation
│   ├── research/                  # ResearchSection, ResearchPanel, CompetitorCard, MarketFactRow, Sources, SourceLink
│   ├── score/                     # ScoreCard, ParamBar, BandBadge
│   ├── account/                   # AccountMenu, WorkspaceSwitcher, NewWorkspaceDialog, UserAvatar (square), ThemeSegment
│   └── settings/                  # SettingsSheet, SettingsShortcut (⌘,) + one panel per tab (keys: KeysPanel, key-fields, saved-key, run-limits-fields)
├── lib/
│   ├── keys/                      # keyReadiness (LLM block reason, Exa missing), key-gate and 402 messages
│   ├── api/                       # client.ts (browser), server-client.ts (server), create-client.ts, errors.ts, workspace.ts, schema.d.ts (generated), queries/, mutations/
│   ├── events/                    # useRunEvents, event Zod schemas (schemas.ts), runReducer (reducer.ts), node/stage labels
│   ├── interview/                 # buildInterviewThread: questions and answers for the thread
│   ├── research/                  # research view mapping: safe links, domains, overlap %, confidence, source chips
│   ├── schemas/                   # Zod form schemas (settings-forms.ts, idea-form.ts, answer.ts)
│   ├── settings/                  # tab parsing (`?settings=`), useOpenSettings, key-test failure messages
│   └── utils.ts                   # cn()
└── next.config.ts                 # rewrite /v1/* to the API so the session cookie is first-party
```

## Routes

| Route             | Access    | Screen                                                                                      |
| ----------------- | --------- | ------------------------------------------------------------------------------------------- |
| `/sign-in`        | public    | Split: pitch left, form right (form first on mobile)                                        |
| `/terms`, `/privacy` | public | Terms of Use and Privacy Policy, in the sign-in frame; linked from the sign-in card |
| `/`               | signed in | Empty chat: "What are you building?", suggestions, composer. Send creates the idea (`POST /v1/ideas`), starts a run (`POST /v1/ideas/{id}/runs`, fresh `Idempotency-Key`) and goes to the idea. Above the composer: the key gate line or the Exa banner (see Key Gate) |
| `/ideas/[ideaId]` | signed in | Conversation for the idea's latest run (`GET /v1/ideas/{id}` + `GET /v1/ideas/{id}/runs?limit=1`), the interview (`GET /v1/ideas/{id}/interview`) and the research (`GET /v1/ideas/{id}/research`); no run → Start; unknown or hidden idea → "Idea not found" |
| `?settings=<tab>` | signed in | Opens the settings sheet on any app route. Tabs: `account`, `keys`, `integrations`, `prefs` |

Auth: server-owned Google sign-in (`server-context.md`, Auth and Request Scope). "Continue with Google" is a plain link to `/v1/auth/google/login?redirect_to=<path>`. The web holds no auth SDK and no tokens; the session is an `HttpOnly` cookie. `next.config.ts` rewrites `/v1/*` to `API_ORIGIN` (build-time, also read by server components), so the cookie is first-party and no CORS is needed; `GOOGLE_REDIRECT_URI` therefore points at the web origin. The `(app)` layout calls `GET /v1/auth/me` on the server; a `401` renders `RedirectToSignIn`, which sends the visitor to `/sign-in?redirect_to=<current path>` (a layout cannot read its own path, and there is no `proxy.ts`). Render provider buttons from `GET /v1/auth/providers`; email shows as "Soon". The sign-in page uses the same frame (rails, safe area, ticks) as the app.

## API Client

One `openapi-fetch` client (`lib/api/create-client.ts`) with types generated by `npm run gen:api` (`server/scripts/export_openapi.py` → `lib/api/schema.d.ts`, committed; CI regenerates it and fails on a diff). Browser code uses `apiClient` (same origin, `credentials: "include"`); server components use `await getServerClient()` (`API_ORIGIN`, forwards the incoming cookies). No `Authorization` header anywhere.

- **Headers:** `POST`/`PUT`/`PATCH`/`DELETE` send `X-Metis-Client: web`; every call sends `X-Workspace-Id` from the `metis_workspace` cookie when set.
- **Workspace cookie:** `metis_workspace` holds the chosen workspace id: readable by scripts (not `HttpOnly`), `SameSite=Lax`, `Path=/`, 1 year; helpers in `lib/api/workspace.ts`. A `403 auth.forbidden` on a call that sent the header clears it and refetches, so the server falls back to the personal workspace.
- **Errors:** every non-2xx throws `ApiError {status, code, title, detail, request_id, retryable, errors}`; a body that is not problem+json becomes `common.unexpected`. `errorMessage(err)` and `fieldErrors(err)` (for `setError`) live in `lib/api/errors.ts`.
- **Session expiry:** in the browser `auth.not_signed_in` / `auth.session_expired` clear the query cache, toast "Signed out" once and go to `/sign-in?redirect_to=<path>` (`QueryProvider`). On the server `redirectIfSignedOut(error, path)` redirects the same way; `getMe()` returns `null` instead.
- **Retries:** none on 4xx; up to 2 on a `retryable` 5xx.
- **Hooks:** one per resource in `lib/api/queries/` (`useMe`, `useCurrentWorkspace`, `useWorkspaces`, `useSettings`, `useIdeas` (infinite, cursor), `useIdea`, `useLatestRun`), one per mutation in `lib/api/mutations/` (`useSaveKey`, `useTestKey`, `useDeleteKey`, `useUpdateSettings`, `useCreateWorkspace`, `useSignOutAll`, `useCreateIdea`, `useStartRun`, `useCancelRun`). Idea query keys start `["ideas", workspaceId, …]`; a run's `run_status` events refetch the idea and its latest run. `describeError(err)` turns any thrown value into a message (network failures get a generic line). Workspace-scoped query keys include the workspace id (`queries/keys.ts`), read through `useWorkspaceId()`, which re-renders when `setWorkspaceId` / `clearWorkspaceId` change the cookie. Switching workspace removes every cached query except `me` and refreshes server components. `ApiError.meta` carries the problem's `meta` (`upstreamReason(err)` reads `meta.reason` of a `provider.upstream_error`). SSE does not use this client (`useRunEvents`).

## Design Language

Sharp, compact, quiet. Linear-style density on shadcn neutral tokens.

1. **Square everything.** `--radius: 0`. No `rounded-*` anywhere, including avatars, pills, inputs, tooltips and the send button. Only spinners may be round.
2. **Lines, not shadows.** Structure comes from 1px `border` lines. Shadows only on floating layers (popover, sheet).
3. **Frame and grid.** Content sits in a bordered safe area; lines run edge to edge with `+` ticks where they cross (see Layout).
4. **Neutral first.** Color only for meaning: score bands, status dots, destructive.
5. **Compact.** 13px base, 28–30px controls, 44px header.
6. **Agent text has no bubble.** User messages are filled blocks on the right; agent replies are plain text on the left.

## Tokens

Defined in `app/globals.css` as CSS variables, exposed to Tailwind through `@theme inline` (shadcn v4 convention). Use the utilities (`bg-background`, `text-muted-foreground`, `border-border`), never raw values.

| Token                                  | Light                   | Dark                 |
| -------------------------------------- | ----------------------- | -------------------- |
| `--background`                         | `oklch(1 0 0)`          | `oklch(0.145 0 0)`   |
| `--foreground`                         | `oklch(0.145 0 0)`      | `oklch(0.985 0 0)`   |
| `--card`                               | `oklch(1 0 0)`          | `oklch(0.205 0 0)`   |
| `--muted` / `--secondary` / `--accent` | `oklch(0.97 0 0)`       | `oklch(0.269 0 0)`   |
| `--muted-foreground`                   | `oklch(0.556 0 0)`      | `oklch(0.708 0 0)`   |
| `--primary`                            | `oklch(0.205 0 0)`      | `oklch(0.922 0 0)`   |
| `--primary-foreground`                 | `oklch(0.985 0 0)`      | `oklch(0.205 0 0)`   |
| `--border`                             | `oklch(0.922 0 0)`      | `oklch(1 0 0 / 10%)` |
| `--input`                              | `oklch(0.922 0 0)`      | `oklch(1 0 0 / 15%)` |
| `--ring`                               | `oklch(0.708 0 0)`      | `oklch(0.556 0 0)`   |
| `--destructive`                        | `oklch(0.577 0.245 27)` | same                 |
| `--success`                            | `oklch(0.627 0.17 149)` | same                 |
| `--warning`                            | `oklch(0.75 0.15 70)`   | same                 |
| `--radius`                             | `0`                     | `0`                  |

Layout tokens:

| Token        | Value                                                                       | Use               |
| ------------ | --------------------------------------------------------------------------- | ----------------- |
| `--frame`    | `min(1280px, 100% - 160px)`; `100% - 64px` under 1040px; `100%` under 700px | Safe area width   |
| `--col`      | `760px`; `100%` under 820px                                                 | Chat column width |
| `--header-h` | `44px`                                                                      | App header        |
| `--footer-h` | `32px`                                                                      | App footer        |

Score band colors (the only colored surfaces): `build` = success, `promising` = warning, `advise` = destructive. Badge fill is the color at 18% over transparent; text is the color mixed 70% with foreground.

## Custom Lengths

No px/em/rem literals in class names. Fixed sizes live once, in the `@theme` block of `app/globals.css`, and components use the names. A new length is added there and to the lists in `lib/cn.ts` (the class merger must know it, or `text-*` names are read as colors). `components/ui/` imports `cn` from the package; `next.config.ts` and `tsconfig.json` alias it to `lib/cn.ts`.

| Group          | Names (value)                                                                                                                                                                                                         |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Breakpoints    | `compact` (700px), `stacked` (900px), `guides` (820px): `max-compact:`, `max-stacked:`, `max-guides:`                                                                                                                                                  |
| Font size      | `text-micro` 10, `text-eyebrow` 10.5, `text-meta` 11, `text-note` 11.5, `text-control` 12.5, `text-body` 13, `text-title` 17, `text-score` 28, `text-display` (clamp 24-32, line-height 1.12, tracking -0.03em) |
| Tracking       | `tracking-eyebrow` .12em, `tracking-divider` .08em, `tracking-label` .06em, `tracking-score` -.04em                                                                                                                   |
| Fixed sizes    | `h-control` 30, `h-badge` 18, `h-track` 3, `size-tick` 9                                                                                                                                                              |
| Max widths     | `max-w-pitch` 480, `max-w-headline` 460, `max-w-lead` 400, `max-w-card` 320                                                                                                                                           |
| Grid utilities | `grid-cols-split` (1.1fr 1fr), `grid-cols-score-row` (100px 1fr)                                                                                                                                                      |

## Typography

| Role            | Size / weight                                | Notes                            |
| --------------- | -------------------------------------------- | -------------------------------- |
| Body            | 13px / 400, lh 1.5                           | `text-[13px]` set once on `body` |
| Secondary, meta | 11–12px, muted                               | Timestamps, hints, footer        |
| Section label   | 11px / 500, uppercase, tracking .06em, muted | Settings groups, menu labels     |
| Eyebrow         | 10.5px Geist Mono, uppercase, tracking .12em | Sign-in pitch                    |
| Page title      | 20–24px / 600, tracking -0.02em              | Empty state, sign-in             |
| Score number    | 24px / 600, tabular                          | `/ 100` at 12px muted            |
| Mono            | Geist Mono 11.5–12px                         | Keys, URLs, kbd hints            |

## Spacing and Sizes

4px grid. Prefer `gap-*` over margins.

| Element                   | Size                                                               |
| ------------------------- | ------------------------------------------------------------------ |
| Icon button               | 28×28 (header), 26×26 (composer), 24×24 (message actions)          |
| Button                    | h-30 px-10 text-12; `sm` h-26; `lg` (sign-in) h-32                 |
| Input / select            | h-30 px-8 text-12.5                                                |
| Avatar                    | 24 (header), 28 (menu head), 22 (agent mark)                       |
| Chip (suggestion, source) | h-24 px-8 text-12                                                  |
| Message gap               | 16px; inside agent message 8px                                     |
| Thread padding            | 16px top, 20px sides (16 on mobile)                                |
| Popover                   | w-236, p-3, item h-28                                              |
| Settings sheet            | w-400 (full on mobile), body p-14/16, group gap 10, section gap 18 |
| Switch                    | 28×16, square thumb                                                |

## Layout: Frame and Grid

`components/frame/` renders a fixed background layer (`pointer-events-none`, `z-0`) under the app:

| Piece         | Spec                                                                                                                                                                                                                                |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Side rails    | Areas outside `--frame`, filled with concentric 1px circles (`stroke: foreground` at 9% opacity, r 60→1800 step 16, centre 140px past the outer edge; left at 38% height, right mirrored at 72%). One SVG per side, generated once. |
| Safe area     | `--frame` wide, `bg-background`, `border-x`                                                                                                                                                                                         |
| Column guides | 1px vertical lines at `50% ± --col/2`, full height, through header and footer                                                                                                                                                       |
| Header line   | `border-b` full viewport width at `--header-h`                                                                                                                                                                                      |
| Footer line   | `border-t` full viewport width at `--footer-h` from the bottom                                                                                                                                                                      |
| Input band    | 1px line across the full viewport at the composer's top edge; composer fills the column flush between the guides; footer line closes it                                                                                             |
| Cross ticks   | 9×9 `+` (muted-foreground, 60%) at every frame × line and guide × line crossing                                                                                                                                                     |

Header and footer are transparent so rails show through. Under 820px: hide column guides and their ticks. Under 700px: hide rails and frame ticks, frame is full width without side borders. `html, body { overflow-x: clip }` so the full-width lines never cause horizontal scroll.

## Components

| Component       | Built from               | Behavior                                                                                                                                                                                                                                                   |
| --------------- | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AppHeader`     | flex row in `--frame`    | Logo (20px filled square) + "Metis" + `Beta` badge; right: New idea, `RecentIdeas`, theme toggle, `AccountMenu`                                                                                                                                            |
| `RecentIdeas`   | DropdownMenu             | Icon button (history, `aria-label` "Recent ideas" + tooltip). Lists the workspace's ideas newest first (`GET /v1/ideas`, 10 per page): title + stage, links to `/ideas/{id}`; "Load more" follows `next_cursor`; loads when first opened; "No ideas yet" when empty |
| `UserBubble`    | Bubble (filled)          | `bg-secondary`, px-10 py-6, max 80%, right aligned, `whitespace-pre-wrap`                                                                                                                                                                                  |
| `AgentMessage`  | Message + Bubble `ghost` | 22px bordered mark + "Metis" label + the idea's stage badge; children: StepList, Sources, ScoreCard, text, run outcome (error row with Retry, "Run stopped.", "Run finished.", question placeholder). Message actions (copy, regenerate, thumbs up) come later |
| `Shimmer`       | shadcn.io Shimmer        | Current step label while nothing has streamed                                                                                                                                                                                                              |
| `StepList`      | shadcn.io Task           | Bordered box; one row per specialist run (a node that runs twice gets two rows); spinner → check when done, `–` and "(skipped)" when a `notice` says the node did no work; tool names under the row in mono                                                                                                              |
| `Sources`       | shadcn.io Sources        | Square chips under the steps: favicon letter + domain, one per source domain, at most 5 then "+N more"; each is an external link built from the fetched research (the server emits no research events yet) |
| `ResearchPanel` | native `<details>`       | Collapsible block (open by default) in the agent message: "Research · N competitors · M facts", the summary, competitor cards (favicon letter, name link, what it does, pricing, overlap %, source link), market-fact rows (claim, quote, source link, date, confidence High / Medium / Low) and trends / risks. Source links are http(s) only, `target="_blank" rel="noopener noreferrer nofollow"`; anything else shows "No source". Empty before research exists (`404 research.not_found`); a load error shows an alert with Retry once a Researcher step has started |
| `QuickReplies`  | outline chips            | Above the textarea while a question is pending: "Skip" (sends `skip`) and "That's enough" (sends `that's enough`) send at once; "Stop run" on the right stops the run (it waits for an answer, so Stop is not the send button) |
| `ApprovalPrompt`| bordered group           | An `approval` interrupt: action, details, Approve / Reject (resume with `true` / `false`); the choice shows as the user's message |
| `InterviewMessages` | AgentMessage + UserBubble | Questions as agent messages and answers as user bubbles, between the idea and the run's message; only `asked` turns show |
| `KeyGateNotice` | bordered row             | One `role="status"` row above the composer's textarea (inside the form padding): `TriangleAlert` (`--warning`) and the reason when the LLM key blocks a run, else an `Info` icon and the Exa banner; a plain "Open API keys" link (`?settings=keys`). Nothing when both keys are fine. See Key Gate |
| `RunNotices`    | bordered rows            | Under the step list: one quiet row per server `notice` (`Info` icon, the text as plain text; no destructive color). `research.skipped_no_exa` adds an "Add an Exa key for a new run" link |
| `ScoreCard`     | Card                     | Total, `BandBadge`, six `ParamBar`s (label, 4px track, value); bars animate width on mount; click a bar for reason + evidence + confidence                                                                                                                 |
| `Suggestions`   | shadcn.io Suggestion     | Outline chips above the composer; click sends the label                                                                                                                                                                                                    |
| `Composer`      | shadcn.io Prompt Input   | Auto-growing textarea (1 line → 180px, `field-sizing: content`). Right: "Enter to send" hint + 26px send. Send turns into Stop while a run is active, then "Stopping…" until the run reports `cancelled`. Enter sends, Shift+Enter new line. Inline error under the textarea. Tools (attach, web research, mention a past idea, model) are not shown until their server features exist. On the idea page it answers the run's pending question (placeholder "Type your answer", 1–10,000 characters, Zod); it is disabled while Metis works ("Metis is working…"), while an approval waits ("Approve or reject above") and when there is nothing to answer |
| `AccountMenu`   | DropdownMenu             | Head (square avatar, name, email), workspace switcher (a submenu: workspaces, New workspace), Settings (⌘,), API keys (saved count `n/2`), Integrations, Theme segment, Sign out. No Docs item until a docs URL exists                                      |
| `SettingsSheet` | Sheet `side="right"`     | Open while `?settings=<tab>` is on the URL (unknown tab → `account`); tabs: Account, API keys, Integrations, Preferences. Sticky footer Cancel / Save changes only on API keys (owners). Esc and scrim close it; focus lands on the open tab and returns to the trigger. |
| `Tooltip`       | Tooltip                  | Inverted (foreground bg), 11px, square, above the trigger                                                                                                                                                                                                  |

## Settings Content

| Tab          | Fields                                                                                                                                                          |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Account      | Name, email and workspace name + role (all read-only: no server route edits them); Sign out all devices (`POST /v1/auth/logout-all`, confirm dialog)           |
| API keys     | Per kind (LLM, Exa): saved key as `masked` with Test / Replace / Remove, or the input form (LLM: base URL, model, key; Exa: key). Run limits: budget per run (USD, 0–100) and max steps per run (1–200), saved with the sheet's Save (`PATCH /v1/settings` with `version`; 409 reloads). Members see everything read-only and can Test |
| Integrations | "Soon" placeholder (Linear, Notion). Connect flows come with the integrations screens                                                                           |
| Preferences  | Theme segment only. Weekly market watch, score alerts and skip-known-questions have no server settings yet and are not shown                                    |

Keys are never read back. Inputs for secrets are `type="password"` and empty after save.

## Live Run Events → UI

`useRunEvents(runId, seed)` (`lib/events/`) opens `EventSource("/v1/runs/{id}/events?workspace_id=<id>", {withCredentials: true})`: the session cookie authenticates, and the workspace goes in the query because `EventSource` sends no headers (omitted when no workspace is chosen, so the server uses the personal one). No stream token. Each frame's `data` is the envelope `{run_id, type, data, ts}`, parsed with Zod; unknown event names, bad JSON and payloads that fail the schema are ignored. Valid events go through the pure `runReducer`, seeded from the run view (`status`, `error`, `pending_interrupt`). The stream replays from the start on every page load (that is how a reload restores the steps), and the browser resends `Last-Event-ID` on reconnect, so nothing repeats. The hook closes the source after a terminal `run_status` (`succeeded`, `failed`, `cancelled`) or a server `event: error` frame. Mount it under `key={runId}`.

Server event names (`core.events.RunEventType`), kept as is:

| Event                            | Payload                                                       | UI effect                                                                                                  |
| -------------------------------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `run_status`                     | `{status, error?: {code, message}}`                           | Composer busy (`queued`, `running`, `awaiting_user` → Stop); `failed` → error row with `error.message` and Retry; `cancelled` → "Run stopped."; `succeeded` → "Run finished."; refetches idea (stage) and run |
| `node_started` / `node_finished` | `{node}`                                                      | Add a step row (spinner) / mark the node's latest row done; a start while that row runs is a no-op           |
| `tool_call`                      | `{node, name}`                                                | Tool name under the node's latest row (once per name)                                                      |
| `token`                          | `{node, text}`                                                | Append to the agent text (sanitized markdown) with a caret while `running`                                 |
| `notice`                         | `{code, text}`                                                | A `RunNotices` row (one per code; a replay shows it again). `research.skipped_no_exa` also marks the Researcher's step skipped. A step still running when the run `succeeded` closes as done |
| `score`                          | `{score_run_id, total, band}`                                 | Ignored for now (unknown event names are dropped); the score card in SHIP-245 reads the score by refetch |
| `interrupt`                      | `{type: "question", question}` or `{type: "approval", action, details?}` (server also sends `{type: "advice_decision", score_run_id, total, band, suggestion_ids}`; no UI yet, ignored) | A question joins the interview thread and enables the composer; an approval shows `ApprovalPrompt`. Answers go to `POST /v1/runs/{id}/resume` |

Not emitted yet, added with their features: step progress (`current/total`), research items (live source chips), score params and totals as live events (the `score` event only announces a stored score). Research arrives by refetch instead: `GET /v1/ideas/{id}/research` reloads when a `researcher` step finishes and when the run ends.

While a run works and no text has streamed, a `Shimmer` shows the running step ("Interviewer…"; "Researching… <tool name>" for the Researcher), else "Starting…" / "Thinking…". The server sends `retry: 3000` and a `: ping` every 15 s; a finished run whose stream expired gets one synthetic `run_status` frame.

## Interview and Research

- **Thread order:** the idea (user bubble), then the interview (each question an agent message, each answer a user bubble), then the run's agent message (steps, research, text, outcome).
- **Interview source:** past turns come from `GET /v1/ideas/{id}/interview` (only `asked` turns show); the run's current question comes from the stream or `pending_interrupt`. An answer sent from the page shows at once (tied to the interrupt it answers, `RunState.interruptCount`, so a repeated question is asked again) and is taken back, with its text, if the call fails; the turns refetch on every new interrupt and when the run ends.
- **Answering:** Enter sends, Shift+Enter adds a line; the composer stays disabled until `run_status: running`. `409 run.invalid_state` refetches the run and says "This run already moved on."
- **Research:** shown inside the agent message under the steps (Sources chips, then the collapsible `ResearchPanel`); no side panel or tab. Mobile needs no extra layout because it sits in the single column.

## Key Gate

The server refuses a run unless the LLM key is saved and its last test passed (`402 provider.llm_not_ready`), and skips research without an Exa key (`notice`). The web mirrors both from `GET /v1/settings` (`lib/keys/readiness.ts`, `useKeyGate()`):

- **LLM block:** reasons `not_configured`, `not_tested`, `test_failed` (the server's `meta.reason`). The `/` composer is read-only with Send disabled; Start (idea with no run) and Retry (failed run) are disabled and `aria-describedby` the `KeyGateNotice`. Text: "Add an LLM key to start." / "Test your LLM key to start." / "Your LLM key failed its last test."
- **Exa banner:** with a ready LLM key and no Exa key, one row on `/` and on an idea with no run: "Metis will interview you but skip research: Exa isn't set up. Add a key in Settings to include it." Not on a run in progress; not dismissible.
- **Fail open:** while settings load or fail, nothing is blocked and no banner shows; the server's `402` is the backstop. A `402` shows the same text (unknown reason → the server's `detail`), refetches settings, and on `/` goes in the "run did not start" toast with an "Open API keys" action.
- **Live:** saving, testing or removing a key already invalidates the settings query, so the gate follows without a reload.
- The Settings link is `<Link href="?settings=keys">`, not `useOpenSettings`: that hook reads `useSearchParams`, which cannot render on `/` without a Suspense boundary.

## Ideas

- **Title:** the composer is free text; the title is its first non-empty line, trimmed and cut to 120 characters, and must be at least 3 characters. Raw text is 10–10,000 characters after trimming (`lib/schemas/idea-form.ts`, matching the server).
- **Start and Retry:** every start sends a new `Idempotency-Key` (UUID). `409 run.already_running` shows "A run is already in progress for this idea." inline and refetches the latest run. If the idea is created but its first run fails to start, the idea page shows Start.
- **Stage:** the badge shows the idea's `stage`; it moves only when the server changes the idea's stage.

## States

- **Loading:** Shimmer for agent work, skeleton lines (square) for lists. No full-page spinners.
- **Empty:** centered title + one line + suggestions.
- **Errors:** API errors are problem+json; show `title` / `detail` inline near the action, toast only for background failures. Field errors from `errors[]` map to form fields.
- **Disabled:** 35–50% opacity, `cursor-not-allowed`.

## Accessibility

- Every icon-only button: `aria-label` and tooltip.
- Visible focus: 2px `ring` outline, offset 2px; inputs show a 3px ring at 20–25% opacity.
- Thread is `aria-live="polite"`; menus support arrow keys and Esc; sheet traps focus and returns it to the trigger.
- Respect `prefers-reduced-motion`: no shimmer, caret blink, bar or slide animations.
- Contrast: body text uses `foreground`, never `muted-foreground` below 12px on `muted` backgrounds.

## Motion

| What         | Duration / easing                |
| ------------ | -------------------------------- |
| Hover, color | 120–150ms                        |
| Popover in   | 140ms, fade + 4px rise           |
| Sheet in     | 250ms `cubic-bezier(.2,.7,.2,1)` |
| Message in   | 250ms, fade + 6px rise           |
| Score bars   | 800ms width, same curve          |

## Rules

- Tailwind + shadcn only. No inline styles except CSS variables, no CSS modules, no hex, no px/em/rem literals in class names (see Custom Lengths).
- No `rounded-*` classes. If a shadcn component adds one, override via the `--radius` token, not by editing `components/ui/`.
- Validate every form with Zod and every SSE payload with Zod before use.
- API types come only from the generated client; regenerate on server schema change.
- Light and dark must both match the samples before a UI PRD is done.
