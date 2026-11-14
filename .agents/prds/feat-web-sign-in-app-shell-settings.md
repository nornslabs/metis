# PRD: feat-web-sign-in-app-shell-settings

Linear: SHIP-219 · https://linear.app/heimdallabs/issue/SHIP-219/12-web-sign-in-app-shell-and-settings-page

## Problem / Goal

The web app currently has only a default Next.js landing page. Users cannot sign in, and there is no app shell (persistent layout with navigation, workspace switcher, user menu) or settings page to configure BYO keys and workspace settings. The server's JWT auth (SHIP-216) and provider keys / workspace settings (SHIP-217) are ready and need a web frontend.

Goal: implement Auth.js sign-in, an app shell that wraps all authenticated routes, and a settings page where users can manage their BYO LLM/Exa keys and workspace settings. The web app mints a short-lived HS256 API token (using `AUTH_JWT_SECRET`/`AUTH_JWT_AUDIENCE` from the server) that it sends as `Authorization: Bearer` on every API call.

## User stories

1. As a new user, I want to click "Sign in" and be redirected to an Auth.js provider (GitHub, Google, or email magic link), so that I can authenticate without a Metis password.
2. As a signed-in user, I want an app shell with a sidebar navigation (Ideas, Settings), a workspace switcher, and a user menu (profile, sign out), so that I can move around the app and know which workspace I'm in.
3. As a signed-in user, I want the app shell to persist across route changes and show the current workspace name/role, so that I don't lose context.
4. As a user, I want a Settings page where I can add, test, and delete my BYO LLM key (OpenAI-compatible) and Exa key, so that Metis can run interviews and research for me.
5. As a user, I want the Settings page to show my workspace settings (run budget, max steps), so that I can tune how much Metis spends per run.
6. As a user, I want key tests to run against the API (`POST /v1/settings/keys/{kind}/test`) and show success/error inline, so that I know my keys work before saving.
7. As a user, I want masked keys displayed (first 3 + `…` + last 4), so that I can recognise my key without exposing it.
8. As a workspace owner, I want to edit workspace settings (run budget USD, max steps), so that I control the workspace's spend and depth.
9. As a workspace member (non-owner), I want to see but not edit workspace settings and provider keys, so that only owners control spend.
10. As a developer, I want the web app to mint a short-lived HS256 JWT (the "API token") on the client and send it as `Authorization: Bearer` on every API request, so that the server's JWT verification (SHIP-216) works without the server ever seeing Auth.js JWEs.
11. As a developer, I want TanStack Query for data fetching and mutations, with the API token injected automatically, so that all API calls are typed and authenticated.
12. As a developer, I want the sign-in page, app shell, and settings page to use Tailwind + shadcn/ui only, with light/dark support via theme tokens, so that the UI is consistent and maintainable.

## Requirements

### 1. Auth.js Configuration (`web/lib/auth.ts` or similar)

- Configure Auth.js (NextAuth v5) with providers: GitHub, Google, Email (magic link).
- Use `AUTH_SECRET` from env for session encryption.
- Callbacks:
  - `jwt`: include `sub`, `email`, `name`, `picture`, `access_token` (if OAuth), and mint a short-lived HS256 **API token** for the server using `AUTH_JWT_SECRET`/`AUTH_JWT_AUDIENCE` (same values the server expects). The API token `exp` = now + 5 min; `aud` = `AUTH_JWT_AUDIENCE`; `sub` = user's Auth.js `sub`. Store it in the JWT token so the client can read it.
  - `session`: expose the API token and user info to the client via `useSession()`.
- Pages: `/auth/signin`, `/auth/error`, `/auth/callback/*`.
- Session strategy: `jwt` (stateless, token in cookie).
- Cookie settings: `httpOnly`, `secure` in prod, `sameSite: 'lax'`.

### 2. API Token Minting (client-side utility)

- A small utility (`web/lib/api-token.ts`) that reads the API token from the Auth.js session (exposed via `useSession()`) and returns it.
- The token is a plain HS256 JWT signed with `AUTH_JWT_SECRET` (same secret the server uses). The web app has this secret in its env (`AUTH_JWT_SECRET`).
- **Important**: The server never decrypts Auth.js JWEs. The web app mints its own short-lived HS256 token for API calls.

### 3. API Client with TanStack Query (`web/lib/api.ts`)

- Generate the TypeScript API client from the server's OpenAPI schema (`openapi-typescript` + `@tanstack/react-query`).
- Create a `fetch` wrapper that:
  - Reads the API token from the Auth.js session (via the utility above).
  - Adds `Authorization: Bearer <api-token>` header.
  - Adds `X-Workspace-Id` header (read from a client-side workspace context/store, default: personal workspace from `/v1/me`).
  - Handles 401 by triggering a session refresh (Auth.js handles this via `useSession().update()`).
- Export typed hooks for all `/v1` endpoints (ideas, settings, keys, workspaces, etc.).

### 4. App Shell (`web/app/(app)/layout.tsx`)

- Route group `(app)` for all authenticated routes.
- Layout wraps children in a persistent shell:
  - **Sidebar** (desktop): fixed left, 244px wide (matches `--sidebar-width` in globals.css), with:
    - Logo/brand at top.
    - Navigation: "Ideas" (link to `/ideas`), "Settings" (link to `/settings`).
    - Workspace switcher: dropdown showing current workspace name + role; clicking opens a list of user's workspaces (from `/v1/me` or `/v1/workspaces`) to switch.
    - Collapsible to icon-only rail on mobile (< 1024px).
  - **Top bar** (mobile): shows workspace switcher, user menu, hamburger to open sidebar.
  - **User menu** (top right): avatar/initials, name, email, "Profile" (link to `/settings`), "Sign out" (calls Auth.js signOut).
  - **Main content area**: flexible, with proper margins for sidebar.
- The shell fetches `/v1/me` on mount (via TanStack Query) to populate user, workspaces, and current workspace.
- Workspace switch updates `X-Workspace-Id` header for subsequent API calls (store in React Context or Zustand).
- Responsive: sidebar collapses to rail on mobile; top bar appears on mobile only.

### 5. Sign-in Page (`web/app/(auth)/signin/page.tsx`)

- Route group `(auth)` for public auth routes.
- Clean, centered sign-in page with:
  - Metis logo.
  - "Sign in with GitHub", "Sign in with Google", "Sign in with Email" buttons.
  - Uses Auth.js `signIn()` from `next-auth/react`.
  - Redirects to `/ideas` (or intended destination) after sign-in.

### 6. Settings Page (`web/app/(app)/settings/page.tsx`)

- Requires authentication (inside `(app)` route group).
- Two tabs/sections: **Provider Keys** and **Workspace Settings**.

#### Provider Keys tab
- List of key kinds: `llm` (OpenAI-compatible), `exa`.
- For each kind:
  - If key exists: show masked key (first 3 + `…` + last 4), "Test" button, "Delete" button.
  - If no key: show "Add key" button → opens a dialog with:
    - Input for the key (password type, show/hide toggle).
    - "Test & Save" button → calls `PUT /v1/settings/keys/{kind}` then `POST /v1/settings/keys/{kind}/test`.
    - On test success: show green checkmark, close dialog, refresh list.
    - On test failure: show error inline, keep dialog open.
- Only owners see "Add", "Test", "Delete"; members see masked key only (read-only).

#### Workspace Settings tab
- Shows current workspace name, role.
- If owner: editable fields for `run_budget_usd` (number, 0.01–100, step 0.01) and `max_steps` (integer, 1–200).
- "Save" button → `PATCH /v1/settings`.
- If member: fields are read-only with a note "Only owners can change workspace settings".
- Shows `version` (for optimistic locking).

### 7. Protected Route Middleware (`web/middleware.ts`)

- Next.js middleware that checks for a valid Auth.js session on all `(app)` routes.
- No session → redirect to `/auth/signin?callbackUrl=...`.
- Valid session → allow through.

### 8. Environment Variables

Add to `.env.example` (web):
```
# Auth.js
AUTH_SECRET=                       # generate with `openssl rand -base64 32`
AUTH_JWT_SECRET=                   # same as server's AUTH_JWT_SECRET
AUTH_JWT_AUDIENCE=metis-api        # same as server's AUTH_JWT_AUDIENCE

# OAuth providers (optional, at least one required)
AUTH_GITHUB_ID=
AUTH_GITHUB_SECRET=
AUTH_GOOGLE_ID=
AUTH_GOOGLE_SECRET=
AUTH_EMAIL_SERVER=                 # SMTP URL for magic links
AUTH_EMAIL_FROM=

# API
NEXT_PUBLIC_API_URL=http://localhost:8000/v1
```

### 9. OpenAPI Client Generation

- Add a script to generate the TypeScript API client from the server's OpenAPI schema (served at `/v1/openapi.json` or similar).
- Run during `npm run build` or as a separate `npm run generate:api` script.
- Generated types in `web/lib/api/generated/`.

## Out of scope

- The Auth.js providers themselves (GitHub, Google, Email) — just configuration.
- Server-side auth, JWT verification, provider keys API, workspace settings API (already done in SHIP-216, SHIP-217).
- Ideas CRUD, interview, research, scoring, planning, Linear export (later PRDs: SHIP-218+).
- Notion integration, HLD generation, market watch, learning agent (out of scope for MVP).
- Email/Slack alerts, leaderboard, paid plans.
- Mobile app or CLI.

## Touches

`web/lib/auth.ts` (new), `web/lib/api-token.ts` (new), `web/lib/api.ts` (new), `web/lib/api/generated/` (generated), `web/app/(auth)/signin/page.tsx` (new), `web/app/(app)/layout.tsx` (new), `web/app/(app)/settings/page.tsx` (new), `web/app/(app)/ideas/page.tsx` (placeholder, new), `web/components/app-shell/` (new: Sidebar, TopBar, WorkspaceSwitcher, UserMenu), `web/components/settings/` (new: ProviderKeysTab, WorkspaceSettingsTab, KeyDialog), `web/middleware.ts` (new), `web/package.json` (add `next-auth@beta`, `@tanstack/react-query`, `zod`, `openapi-typescript`, `openapi-fetch` or similar), `web/tsconfig.json` (path aliases for generated client), `.env.example` (web section), `.agents/ctx/architecture.md` (auth flow), `.agents/ctx/server-context.md` (API token format, workspace header).

## Dependencies

- `feat-jwt-auth` (SHIP-216): **done**. Provides server-side JWT verification, `/v1/me`, `/v1/workspaces`, workspace scoping via `X-Workspace-Id`.
- `feat-provider-keys` (SHIP-217): **done**. Provides `GET/PATCH /v1/settings`, `PUT/DELETE /v1/settings/keys/{kind}`, `POST /v1/settings/keys/{kind}/test`, owner-only writes.
- Blocks: `feat-ideas-crud` (SHIP-218), `feat-llm-gateway` (SHIP-220), `feat-mcp-connections` (SHIP-231).

## Acceptance criteria

- [ ] Auth.js configured with at least one provider (GitHub); sign-in works end-to-end.
- [ ] Middleware protects all `(app)` routes; unauthenticated users redirect to sign-in.
- [ ] App shell renders on all authenticated routes with sidebar, workspace switcher, user menu.
- [ ] Workspace switcher lists user's workspaces (from `/v1/me`) and switches `X-Workspace-Id` header.
- [ ] Settings page loads provider keys (masked) and workspace settings from API.
- [ ] Owner can add, test, delete LLM and Exa keys; test calls `/test` endpoint and shows result.
- [ ] Member sees keys/settings read-only.
- [ ] Owner can edit run budget and max steps; save calls `PATCH /v1/settings`.
- [ ] API token minted client-side (HS256, `AUTH_JWT_SECRET`/`AUTH_JWT_AUDIENCE`), sent as `Authorization: Bearer` on all API calls.
- [ ] TanStack Query hooks generated from OpenAPI schema; all settings mutations use typed hooks.
- [ ] UI uses Tailwind + shadcn/ui only; light/dark modes work via theme tokens.
- [ ] `npm run lint`, `npm run typecheck`, `npm run build` pass.
- [ ] `architecture.md` and `server-context.md` updated with web auth flow and API token format.

## Open questions

None. Resolved 2026-11-14:

1. **Auth.js provider**: All three (GitHub, Google, Email magic link). Maximum flexibility for the hackathon.
2. **API token minting location**: Server-side in Auth.js `jwt` callback. Token available immediately in `session.apiToken`.
3. **Workspace switch persistence**: Persist in localStorage keyed by user ID. User returns to their last workspace.
4. **Settings page structure**: Tabs on `/settings`. Single page feel, simpler routing.
5. **Key test UX**: Separate "Test" button for existing keys. Allows re-testing without re-entering the key.

## Status

done