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
| Components    | shadcn/ui (`base-color: neutral`, `radius: 0`), Radix primitives                        | Generated into `components/ui/` (protected)                             |
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
│   ├── frame/                     # AppFrame, SideRails, GridGuides, CrossTick
│   ├── chat/                      # Thread, UserBubble, AgentMessage, StepList, Sources, Composer, Suggestions, Shimmer
│   ├── score/                     # ScoreCard, ParamBar, BandBadge
│   ├── account/                   # AccountMenu, WorkspaceSwitcher, ThemeSegment
│   └── settings/                  # SettingsSheet + one panel per tab
├── lib/
│   ├── api/                       # client.ts (openapi-fetch), schema.d.ts (generated), queries/, mutations/
│   ├── events/                    # useRunEvents, event Zod schemas, reducer to UI parts
│   ├── schemas/                   # Zod form schemas
│   └── utils.ts                   # cn()
└── next.config.ts                 # rewrite /v1/* to the API so the session cookie is first-party
```

## Routes

| Route             | Access    | Screen                                                                                      |
| ----------------- | --------- | ------------------------------------------------------------------------------------------- |
| `/sign-in`        | public    | Split: pitch left, form right (form first on mobile)                                        |
| `/`               | signed in | Empty chat: "What are you building?", suggestions, composer                                 |
| `/ideas/[ideaId]` | signed in | Conversation for the idea's latest run                                                      |
| `?settings=<tab>` | signed in | Opens the settings sheet on any app route. Tabs: `account`, `keys`, `integrations`, `prefs` |

Auth: server-owned Google sign-in (`plans/server-auth-google.md`). "Continue with Google" is a plain link to `/v1/auth/google/login?redirect_to=<path>`. The web holds no auth SDK and no tokens; the session is an `HttpOnly` cookie. The `(app)` layout calls `GET /v1/me` on the server; `401` redirects to `/sign-in`. Mutations send `X-Metis-Client: web`. Render provider buttons from `GET /v1/auth/providers`; email shows as "Soon".

> `architecture.md` still says Auth.js. If the auth plan is accepted, update `architecture.md` in the same change.

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
| `AppHeader`     | flex row in `--frame`    | Logo (20px filled square) + "Metis" + `Beta` badge; right: New idea, theme toggle, `AccountMenu`                                                                                                                                                           |
| `UserBubble`    | Bubble (filled)          | `bg-secondary`, px-10 py-6, max 80%, right aligned, `whitespace-pre-wrap`                                                                                                                                                                                  |
| `AgentMessage`  | Message + Bubble `ghost` | 22px bordered mark + "Metis" label; children: StepList, Sources, ScoreCard, text, actions (copy, regenerate, thumbs up)                                                                                                                                    |
| `Shimmer`       | shadcn.io Shimmer        | Current step label while nothing has streamed                                                                                                                                                                                                              |
| `StepList`      | shadcn.io Task           | Bordered box; each step spinner → check when done                                                                                                                                                                                                          |
| `Sources`       | shadcn.io Sources        | Square chips: favicon letter + domain; "+N more"                                                                                                                                                                                                           |
| `ScoreCard`     | Card                     | Total, `BandBadge`, six `ParamBar`s (label, 4px track, value); bars animate width on mount; click a bar for reason + evidence + confidence                                                                                                                 |
| `Suggestions`   | shadcn.io Suggestion     | Outline chips above the composer; click sends the label                                                                                                                                                                                                    |
| `Composer`      | shadcn.io Prompt Input   | Auto-growing textarea (1 line → 180px). Icon-only tools: attach, web research toggle (`aria-pressed`), mention a past idea, model. Right: "Enter to send" hint + 26px send. Send turns into stop while a run is active. Enter sends, Shift+Enter new line. |
| `AccountMenu`   | DropdownMenu             | Head (avatar, name, "Signed in with Google"), workspace switcher, Settings (⌘,), API keys (count), Integrations, Theme segment, Docs, Sign out                                                                                                             |
| `SettingsSheet` | Sheet `side="right"`     | Tabs: Account, API keys, Integrations, Preferences. Sticky footer Cancel / Save changes. Esc and scrim close it.                                                                                                                                           |
| `Tooltip`       | Tooltip                  | Inverted (foreground bg), 11px, square, above the trigger                                                                                                                                                                                                  |

## Settings Content

| Tab          | Fields                                                                                                                                                          |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Account      | Display name; email (read-only, from Google); workspace name; Sign out all devices (`POST /v1/auth/logout-all`); Delete workspace (destructive, confirm dialog) |
| API keys     | LLM base URL, model, API key (write-only: shows "Saved, ends in xxxx", Replace); Exa key with Test; monthly spend limit                                         |
| Integrations | Linear (status, team select), Notion (Connect). Connect opens the MCP OAuth flow                                                                                |
| Preferences  | Theme segment; weekly market watch; score change alerts; skip known interview questions                                                                         |

Keys are never read back. Inputs for secrets are `type="password"` and empty after save.

## Live Run Events → UI

`useRunEvents(runId)` opens `GET /v1/runs/{id}/events`, parses each event with a Zod schema and feeds a reducer that builds the agent message. Unknown events are ignored.

| Event                             | UI effect                                                                               |
| --------------------------------- | --------------------------------------------------------------------------------------- |
| `run.status`                      | Composer busy state; stage label                                                        |
| `step.started` / `step.finished`  | Add step row (spinner) / mark it done                                                   |
| `step.progress`                   | Shimmer text, optional `current/total`                                                  |
| `tool.called`                     | Step row detail (summary only)                                                          |
| `token`                           | Append streamed text with caret                                                         |
| `research.item`                   | Add a source chip                                                                       |
| `score.param` / `score.completed` | Fill a ParamBar / render total and band                                                 |
| `run.awaiting`                    | Stop streaming; show the question and suggestion chips; composer answers resume the run |
| `run.finished`                    | Clear busy state; show message actions                                                  |
| `run.failed`                      | Inline error row with `detail`; Retry when `retryable`                                  |

Reconnect with `Last-Event-ID`; the server pings every 15 s.

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

- Tailwind + shadcn only. No inline styles except CSS variables, no CSS modules, no hex.
- No `rounded-*` classes. If a shadcn component adds one, override via the `--radius` token, not by editing `components/ui/`.
- Validate every form with Zod and every SSE payload with Zod before use.
- API types come only from the generated client; regenerate on server schema change.
- Light and dark must both match the samples before a UI PRD is done.
