# PRD: feat-web-shell-settings

Linear: SHIP-224 · https://linear.app/heimdallabs/issue/SHIP-224/123-app-shell-account-menu-and-settings-sheet

Milestone: M1 — Identity and workspaces. Branch: `feat/web-shell-settings`. Parent: SHIP-219. Blocked by SHIP-221 and SHIP-222.

## Problem / Goal

After SHIP-221 and SHIP-222 a user can sign in and the web has a typed client, but there is no app around them: no frame, header, account menu or way to add the BYO LLM and Exa keys a run needs. Without keys, no idea can run.

Goal: the framed, responsive app shell every later screen lives in, the account menu (with workspace switcher and sign-out), and the settings sheet (`?settings=<tab>`) where a user saves, tests and removes keys and sets the run budget.

## User stories

1. As a signed-in user, I want a framed app with a header, so that I always know where I am and can reach the main actions.
2. As a user, I want the logo, "Metis" and a `Beta` badge in the header, so that I know the product and its stage.
3. As a user, I want a "New idea" button in the header, so that I can start an idea from anywhere.
4. As a user, I want a theme toggle in the header, so that I can switch light and dark quickly.
5. As a new user landing on `/`, I want an empty chat state ("What are you building?"), so that I know what to do first.
6. As a user, I want an account menu showing my name, email and avatar, so that I know which account I am using.
7. As a user, I want to see and switch my workspaces from the account menu, so that I work in the right one.
8. As a user, I want to create a workspace from the menu, so that I can separate projects.
9. As a user who switched workspace, I want every following request to use it, and the choice to persist across reloads, so that I do not switch again.
10. As a user, I want Settings in the menu (and ⌘, / Ctrl+,), so that I can open it fast.
11. As a user, I want the API keys item to show how many keys are set, so that I know if setup is done.
12. As a user, I want to sign out from the menu, so that I can end my session.
13. As a user, I want settings as a sheet over the current page, linkable by `?settings=<tab>`, so that I do not lose my place.
14. As a user, I want Esc and a click on the scrim to close the sheet, and focus to return to what opened it, so that it behaves like other dialogs.
15. As a user, I want my name, email and workspace on the Account tab, so that I can check who and where I am.
16. As a user, I want "Sign out all devices", so that a lost laptop loses access.
17. As a workspace owner, I want to save an LLM key with base URL and model, so that runs can call my provider.
18. As a workspace owner, I want to save an Exa key, so that research can search the web.
19. As a user, I want a saved key shown only masked ("Saved, ends in …") with Replace, so that the plaintext is never on screen again.
20. As a user, I want to test a saved key and see success or the upstream reason inline, so that I know it works before I run an idea.
21. As a workspace owner, I want to remove a key, so that I can revoke it.
22. As a workspace owner, I want to set the per-run budget (USD) and the max steps, so that one run cannot overspend.
23. As a user who saved settings while someone else changed them, I want the newer values loaded and to be told, so that I do not overwrite their change.
24. As a workspace member who is not an owner, I want keys and settings read-only with a short note, so that I understand why I cannot edit.
25. As a user, I want invalid input caught before it is sent, with the field highlighted, so that I fix it quickly.
26. As a user, I want an Integrations tab that says "Soon", so that I know Linear/Notion are coming.
27. As a user, I want a Preferences tab with the theme segment, so that theme lives with other preferences.
28. As a user whose session expires mid-use, I want the "Signed out" toast and a redirect, so that I can sign back in.
29. As a phone user (375px), I want the shell and a full-width sheet with no horizontal scroll, so that I can set up on mobile.
30. As a keyboard or screen-reader user, I want labelled icon buttons, tooltips, arrow-key menus and a focus-trapped sheet, so that I can use everything without a mouse.

## Requirements

1. **Frame.** `components/frame/`: `AppFrame` (fixed background layer, safe area, header and footer slots), `SideRails` (concentric-circle SVGs, generated once), `GridGuides`, `CrossTick`, exactly per `ui-context.md` Layout. Breakpoints: under 820px no column guides or their ticks; under 700px no rails or frame ticks, full-width frame without side borders.
2. **Header and footer.** 44px `AppHeader`: logo (20px filled square), "Metis", `Beta` badge; right: New idea (link to `/`), theme toggle, `AccountMenu`. 32px footer per the chat sample. Icon-only buttons have `aria-label` and tooltip.
3. **Empty state.** `(app)/page.tsx`: centered "What are you building?", one line, suggestion chips and a composer rendered but not wired (SHIP-235 wires them; submit is disabled).
4. **Account menu.** `components/account/AccountMenu` (DropdownMenu): head (24/28px square avatar from `avatar_url` or initials, name, "Signed in with Google"); `WorkspaceSwitcher` (`useWorkspaces()`, current from `useCurrentWorkspace()`, select → `setWorkspaceId`, invalidate all queries; "New workspace" → name input → `POST /v1/workspaces` → switch to it); Settings (⌘,) → `?settings=account`; API keys (count of non-null keys from `GET /v1/settings`) → `?settings=keys`; Integrations → `?settings=integrations`; `ThemeSegment` (light/dark/system); Sign out (`useSignOut()` from SHIP-221).
5. **Settings sheet.** `components/settings/SettingsSheet`, Sheet `side="right"`, w-400 (full width on mobile), opened when `?settings=<tab>` is present on any `(app)` route, tab synced to the query param (unknown tab → `account`); closing removes the param (`router.replace`, no history entry per tab change). Esc and scrim close; focus is trapped and returns to the trigger. Sticky footer Cancel / Save changes, shown only on tabs with editable fields; Save is disabled until the form is dirty and valid.
6. **Account tab.** Read-only name, email, workspace name and role. "Sign out all devices" → confirm dialog → `POST /v1/auth/logout-all` → `/sign-in`. No display-name edit, workspace rename or delete (no server routes).
7. **API keys tab.**
   - Per kind (`llm`, `exa`): when set, show masked value ("Saved, ends in …" from `masked`), base URL and model for `llm`, last test result and time; actions Test, Replace, Remove. When not set, show the input form.
   - Save: `PUT /v1/settings/keys/{kind}` with `{value, base_url?, model?}`; `llm` requires base URL (URL) and model (non-empty); secret inputs are `type="password"`, `autocomplete="off"`, and are reset to empty after save. Plaintext is never rendered.
   - Test: `POST /v1/settings/keys/{kind}/test`; success shows a check and the time; `502 provider.upstream_error` shows `meta.reason` inline next to the key.
   - Remove: confirm, then `DELETE /v1/settings/keys/{kind}`.
   - Run limits: `run_budget_usd` (label "Budget per run (USD)", `0 < x ≤ 100`, 2 decimals) and `max_steps` (label "Max steps per run", integer 1–200), saved by the sheet's Save with `PATCH /v1/settings` and the loaded `version`. `409` → reload settings, keep the sheet open, inline "Settings changed elsewhere; reloaded."
   - Role: owners write; members see everything read-only (no Replace/Remove/Save) with "Only workspace owners can change keys." Members can Test.
8. **Integrations tab.** "Soon" placeholder (SHIP-255).
9. **Preferences tab.** `ThemeSegment` only.
10. **Forms.** One Zod schema per form in `lib/schemas/`, `react-hook-form` + `zodResolver`; server field errors via `fieldErrors()` from SHIP-222.
11. **Hooks.** `useSettings()` (`GET /v1/settings`), mutations `useSaveKey`, `useTestKey`, `useDeleteKey`, `useUpdateSettings`, `useCreateWorkspace`, `useSignOutAll`; each invalidates `settings` or `workspaces` on success.
12. **Keyboard.** ⌘, / Ctrl+, opens `?settings=account` on any app route.
13. **Session expiry.** Handled by SHIP-222's client; nothing new here beyond checking it works with the sheet open.

## Out of scope

- Ideas UI, composer behaviour, chat thread (SHIP-235).
- Integrations connect flow (SHIP-255).
- Invites, members list, display-name edit, workspace rename or delete (no server API).
- Preferences beyond theme (weekly market watch, score alerts, skip known questions: no server settings).
- Any server change.

## Touches

- `web/app/(app)/` (`layout.tsx` → `AppFrame`, `page.tsx`)
- `web/components/` (`frame/`, `account/`, `settings/`, `chat/` empty-state pieces only; `ui/` via the shadcn CLI only)
- `web/lib/` (`api/queries/`, `api/mutations/`, `schemas/`)
- `design/samples/metis-chat-shadcn.html` (added, see SHIP-221 open questions)
- `.agents/ctx/ui-context.md` (Settings Content: monthly spend limit → per-run budget and max steps; Account and Preferences rows match what ships)
- `.agents/progress-tracker.md`

## Dependencies

- `feat-web-sign-in` (SHIP-221): draft.
- `feat-web-api-client` (SHIP-222): draft.

## Testing

Seam: the browser against the running local stack (Playwright, SHIP-221's harness), signed in as a real session. Tests drive the UI and check the server state through the API; no component unit tests.

- Workspaces: create one, switch to it, reload → still selected; `GET /v1/workspaces/current` with the sent header returns it.
- Keys: save LLM and Exa keys → masked shown, inputs empty, page source and DOM contain no plaintext; Test → success (provider faked, see Open questions) and failure with `meta.reason`; Remove → form returns.
- Settings: save budget and steps; a stale `version` (changed through the API in the test) → 409 message and reloaded values; invalid values blocked client side.
- Member: a second user added as member sees read-only keys and settings.
- Sheet: `?settings=keys` deep link opens the tab; Esc closes and returns focus; ⌘, opens it.
- Sign out and Sign out all devices → `GET /v1/auth/me` is 401.
- Visual: shell and sheet at 1280px and 375px, light and dark, compared with the chat sample; no horizontal scroll.
- `npm run lint`, `typecheck`, `build` pass.

## Acceptance criteria

- [ ] A user can switch or create a workspace, and API calls follow with the session cookie and `X-Workspace-Id`.
- [ ] Keys can be saved, tested and removed; plaintext is never shown after save.
- [ ] "Sign out" and "Sign out all devices" end the session on the server (`GET /v1/auth/me` returns 401 afterwards).
- [ ] A new user signs in, lands on `/` in their personal workspace, opens `?settings=keys`, saves an LLM key (base URL, model, key) and an Exa key, and sees Test succeed with masked keys shown (SHIP-219 end-to-end criterion).
- [ ] Light and dark both match the chat sample; works at 375px with no horizontal scroll; focus, `aria-label`s and tooltips per `ui-context.md` Accessibility.
- [ ] `npm run lint`, `typecheck`, `build` pass.

## Open questions

None open.

## Resolved

- "Docs" menu item: hidden until a docs URL exists (user, 2026-11-17).
- Test seam: Playwright on the compose stack; key Test success checked by hand against real keys, Playwright asserts only the failure path (unreachable base URL → 502 with `meta.reason`) (user, 2026-11-17).

From the Linear agent notes:

- Account tab omits display name, workspace rename and delete (no server routes).
- "Monthly spend limit" becomes per-run `run_budget_usd` and `max_steps`; `ui-context.md` is fixed in this PRD.
- Preferences other than theme are hidden.

## Status

draft
