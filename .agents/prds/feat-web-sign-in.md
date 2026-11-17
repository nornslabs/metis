# PRD: feat-web-sign-in

Linear: SHIP-221 · https://linear.app/heimdallabs/issue/SHIP-221/121-foundation-and-sign-in-through-the-metis-server

Milestone: M1 — Identity and workspaces. Branch: `feat/web-sign-in`. Parent: SHIP-219 (12 · Web sign-in, app shell and settings sheet). Blocked by SHIP-265 (done).

## Problem / Goal

`web/` is the create-next-app scaffold: Next.js 16, Tailwind 4, one shadcn `Button`, no tokens, no providers, no auth. The server already owns Google sign-in and sets an `HttpOnly`, `SameSite=Lax` session cookie (SHIP-264, SHIP-265, SHIP-267), but nothing in the browser can use it.

Goal: lay the web foundation (stack, tokens, root providers, `/v1` rewrite) and let a user sign in with Google and sign out, entirely through the Metis server. The web holds no auth SDK and never sees a token.

## User stories

1. As a new visitor, I want a sign-in page that explains what Metis does, so that I know why I am signing in.
2. As a visitor, I want a "Continue with Google" button, so that I can sign in with the account I already have.
3. As a visitor, I want only the providers the server offers to appear, so that I never click a button that cannot work.
4. As a visitor, I want email sign-in shown as "Soon", so that I know it is coming but not available.
5. As a visitor whose sign-in failed, I want a short, friendly message on the sign-in page, so that I know what went wrong and can retry.
6. As a visitor who opened a deep link while signed out, I want to land on that page after signing in, so that I do not have to find it again.
7. As a signed-out visitor, I want any app route (`/`, `/ideas/...`) to send me to `/sign-in`, so that I never see a broken, empty app.
8. As a signed-in user, I want to stay signed in across reloads and tabs, so that I sign in once.
9. As a signed-in user, I want to sign out, so that the next person on this machine cannot use my session.
10. As a user, I want the session to live only in an `HttpOnly` cookie, so that a script injected into the page cannot steal it.
11. As a user on a phone (375px), I want the sign-in form first and no horizontal scroll, so that I can sign in on mobile.
12. As a user, I want the page to follow my system light/dark theme, so that it is comfortable to read.
13. As a developer, I want the theme tokens, fonts and providers set once in the root layout, so that later screens only compose components.
14. As a developer, I want `/v1/*` rewritten to the API, so that the session cookie is first-party and no CORS is needed.
15. As a developer, I want the rewrite to pass SSE through unbuffered, so that the live run view (SHIP-235) works through it.
16. As an operator, I want the API origin read from the environment, so that compose, CI and production can point the web at their API.

## Requirements

1. **Stack.** Install `next-themes`, `geist`, `sonner`, `zod`, `react-hook-form`, `@hookform/resolvers`, `@tanstack/react-query`, `openapi-fetch`, `openapi-typescript` (dev), `react-markdown`, `remark-gfm`. shadcn components are added with the CLI into `components/ui/` and never edited. No `next-auth`.
2. **Tokens.** `app/globals.css`: Tailwind import, `tw-animate-css`, `@theme inline` mapping, light and dark variables exactly as in `ui-context.md` Tokens (incl. `--success`, `--warning`, `--radius: 0`), layout tokens (`--frame`, `--col`, `--header-h`, `--footer-h` with their breakpoints), 13px body, `html, body { overflow-x: clip }`.
3. **Root layout.** `app/layout.tsx`: Geist Sans and Geist Mono via the `geist` package, `ThemeProvider` (`attribute="class"`, default `system`), `QueryProvider` (one `QueryClient` per browser session), `Toaster` (bottom center, square). Title "Metis".
4. **Rewrite.** `next.config.ts` rewrites `/v1/:path*` to `${API_ORIGIN}/v1/:path*`, keeping the existing options. `API_ORIGIN` is a server-only env var (no `NEXT_PUBLIC_`), added to `.env.example` and the compose `web` service (`http://api:8000`), replacing the unused `NEXT_PUBLIC_API_URL`. Verify that an SSE response is streamed through the rewrite without buffering; if it is buffered, record it as a blocker for SHIP-235 in the tracker.
5. **Google callback on the web origin.** `GOOGLE_REDIRECT_URI` in `.env.example` becomes `${WEB_BASE_URL}/v1/auth/google/callback` (`http://localhost:3000/...`), so the callback, and the `Set-Cookie` it returns, come through the rewrite on the web origin.
6. **Sign-in page.** `app/(auth)/sign-in/page.tsx`, matching `design/samples/metis-auth-shadcn.html`: pitch left, form right; form first under the mobile breakpoint.
   - Providers come from `GET /v1/auth/providers` (server-side fetch). `google` renders "Continue with Google" as a plain `<a href="/v1/auth/google/login?redirect_to=<path>">`. Email renders disabled with a "Soon" badge.
   - `redirect_to` is taken from the page's own `?redirect_to=` and passed through only if it is a relative path starting with a single `/`; otherwise `/`.
   - `?error=<code>` maps to inline messages: `auth.oauth_state_invalid` → "Your sign-in link expired. Try again.", `auth.oauth_failed` → "Google sign-in failed. Try again.", `auth.email_unverified` → "Your Google email is not verified.", anything else → a generic message.
   - A signed-in visitor to `/sign-in` is redirected to `/`.
7. **App guard.** `app/(app)/layout.tsx` calls a server-only `getMe()`: plain `fetch` of `${API_ORIGIN}/v1/auth/me` forwarding the incoming `cookie` header, `cache: "no-store"`. `401` → `redirect("/sign-in?redirect_to=<current path>")`. Other failures throw to the nearest error boundary. A minimal placeholder `(app)/page.tsx` proves the guard; the shell is SHIP-224. Works with `cacheComponents: true` (cookie reads inside a Suspense boundary, as Next 16 requires).
8. **Sign out.** `useSignOut()` mutation: `POST /v1/auth/logout` with `X-Metis-Client: web` and `credentials: "include"`, then clear the query cache and `router.replace("/sign-in")`. Not yet shown in a menu (SHIP-224); exposed on the placeholder page for manual testing.
9. **No proxy file.** No `middleware.ts` / `proxy.ts`; the layout guard is the only redirect.

## Out of scope

- Typed API client, `ApiError`, query hooks (SHIP-222). `getMe()` stays a plain `fetch` until then.
- App shell, account menu, settings sheet (SHIP-224).
- Email sign-in, invites.
- Any server change other than the `.env.example` / compose values above.

## Touches

- `web/app/` (`layout.tsx`, `globals.css`, `(auth)/sign-in/`, `(app)/layout.tsx`, `(app)/page.tsx`; scaffold `page.tsx` removed)
- `web/components/` (`providers/`, `auth/`; `ui/` via the shadcn CLI only)
- `web/lib/` (`auth/get-me.ts`, `auth/redirect.ts`, `auth/sign-out.ts`)
- `web/next.config.ts`, `web/package.json`, `web/package-lock.json` (npm only)
- `.env.example`, `compose.yaml` (`web` env)
- `design/samples/metis-auth-shadcn.html` (added, see Open questions)
- `.agents/ctx/ui-context.md` (`/v1/me` → `/v1/auth/me`, drop the `plans/server-auth-google.md` reference), `.agents/ctx/architecture.md` if it still names Auth.js

## Dependencies

- `feat-auth-google` (SHIP-265): done.
- `refactor-remove-jwt-auth` (SHIP-267): done.

## Testing

Seam: the browser against the running local stack (`docker compose up`), driven by Playwright. Tests assert what a user sees and what the server reports, not component internals.

- Signed-out visit to `/` and `/ideas/x` → `/sign-in?redirect_to=...`.
- Sign-in page renders only server-listed providers; `?error=auth.oauth_failed` shows its message.
- `redirect_to` sanitising: `//evil.com` and `https://evil.com` fall back to `/` (unit test on the pure helper).
- Sign in (Google faked, see Open questions) → back on the requested path; `document.cookie` does not contain the session cookie.
- Sign out → `/sign-in`; `GET /v1/auth/me` → 401.
- Visual: sign-in at 1280px and 375px, light and dark, compared by eye with the sample; no horizontal scroll at 375px.
- `npm run lint`, `npm run typecheck`, `npm run build` pass.

## Acceptance criteria

- [ ] Sign in with Google and sign out work end to end against the local stack; `GET /v1/auth/me` returns the same user. (sign out verified by e2e; Google round trip needs a manual check with real credentials)
- [x] After sign-in the user returns to the page they first asked for. (login link carries `redirect_to`; the server callback does the redirect, verified by the signed-in redirect test; a real Google round trip is still manual)
- [x] A signed-out visit to `/` or `/ideas/...` redirects to `/sign-in`. (`/ideas/[ideaId]` does not exist yet; the `(app)` layout guards it when SHIP-235 adds it)
- [x] No `next-auth` dependency; no token is readable from JavaScript (`HttpOnly` cookie only).
- [x] SSE passes through the `/v1` rewrite unbuffered (events arrived ~0.7 s apart through a standalone build; no blocker for SHIP-235).
- [x] Sign-in matches the sample in light and dark, at 375px with no horizontal scroll. (differences: no Docs link, no Terms/Privacy line, see Open questions)
- [x] `npm run lint`, `typecheck`, `build` pass; `npm test` (17) and `npm run test:e2e` (9) pass.

## Open questions

1. The sample shows "By continuing you agree to the Terms and Privacy Policy" and a header "Docs" link; neither has a target in the repo. Left out. Recommended: add them when Terms/Privacy pages and a docs URL exist.

## Resolved

- Design samples: the user adds `design/samples/metis-auth-shadcn.html` and `metis-chat-shadcn.html`; no screen is built before they are in the repo (user, 2026-11-17).
- Primitives: keep shadcn `base-nova` on `@base-ui/react`; `ui-context.md` (Stack: "Radix primitives") is updated in this PRD (user, 2026-11-17).
- Test seam: Playwright against the compose stack for flows, Vitest for pure helpers; a real Google login is checked by hand (user, 2026-11-17).

## Implementation notes

- `RedirectToSignIn` (client) does the signed-out redirect: a layout cannot read its own path and there is no `proxy.ts`, so a server `redirect()` could not carry `redirect_to`.
- `export const instant = false` on the `(app)` layout (Cache Components docs, auth guide).
- `components/frame/` holds `FrameBackground`, `SideRails`, `CrossTick`; SHIP-224 adds `AppFrame` and `GridGuides` on top.
- `typecheck` runs `next typegen` first so `PageProps` exists on a clean checkout.
- Compose: `API_ORIGIN` is a build arg (rewrites are baked into the standalone build) and a runtime env.
- e2e (`npm run test:e2e`) needs the compose stack and `docker compose exec postgres`; it seeds a user and one session per test.
- The `User` DTO field is `image` (not `avatar_url`): use it in SHIP-224.

## Status

in progress
