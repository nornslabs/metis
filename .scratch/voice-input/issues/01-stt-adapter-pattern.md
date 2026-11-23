# 01: STT Adapter Pattern

**What to build:** Config-driven STT adapter layer: `STT_PROVIDER` env (values: `sarvam` | `web-speech` | `mock`), adapter factory, `transcribe(audioBlob: Blob): Promise<string>` interface, Zod-validated server config at `@/lib/config/server`, client-safe config at `@/lib/config`, plus a `MockSTTProvider` for tests.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] `STT_PROVIDER` env documented in `.env.example` (defaults to `web-speech`)
- [x] Adapter factory exports `getSTTProvider()` returning object with `transcribe(Blob): Promise<string>`
- [x] Server config validates provider + required credentials (Sarvam needs `SARVAM_API_KEY`)
- [x] Client config exposes provider name only (no secrets)
- [x] `MockSTTProvider` returns configurable transcript for unit tests
- [x] Unit tests: factory returns correct provider per config; unknown provider throws clear error (matches criterion 6, not ticket line 24 which suggested fallback — throwing is safer); mock transcribes deterministically

**Files added:**
- `web/lib/stt/types.ts` — `STTProvider` interface, `STTProviderName` type
- `web/lib/stt/config.server.ts` — Zod-validated server config (`getSTTServerConfig`)
- `web/lib/stt/config.ts` — Client-safe config (`getSTTClientConfig`, provider name only)
- `web/lib/stt/providers.ts` — `MockSTTProvider`, `SarvamSTTProvider`, `WebSpeechSTTProvider`
- `web/lib/stt/factory.ts` — `getSTTProvider()` factory, auto-selects provider by env
- `web/lib/stt/factory.test.ts` — 10 unit tests, all passing

**Provider selection:** `STT_PROVIDER=sarvam` → Sarvam (requires `SARVAM_API_KEY`); otherwise → Web Speech API (free, no key); `mock` for tests.

**Verification:** `npx vitest run` → 285/285 tests pass; `npx tsc --noEmit` → clean.
