# 04: Sarvam STT Provider + Web Speech API Fallback

**What to build:** Two provider implementations behind the `transcribe(Blob): Promise<string>` interface. Provider selection is automatic: if `SARVAM_API_KEY` env is set, use Sarvam; otherwise fall back to browser Web Speech API (free, no key). Tests run against the mock provider (01) — no real microphone or API needed in CI.

**Sarvam provider:** sends the WebM audio blob to Sarvam's STT endpoint with `SARVAM_API_KEY` as Bearer auth, returns the transcript string.

**Web Speech API provider:** uses `webkitSpeechRecognition` / `SpeechRecognition` — records live audio from mic and returns transcript, no blob upload needed. Free by default in Chrome/Edge/Safari.

**Blocked by:** 01 (STT Adapter Pattern) — needs the provider interface and factory

**Status:** ready-for-agent

- [x] `SarvamSTTProvider.transcribe(blob)`: POSTs blob to Sarvam, returns `Promise<string>` — implemented in providers.ts (ticket 01)
- [x] `WebSpeechSTTProvider.transcribe(blob)`: uses `SpeechRecognition`, returns transcript — implemented in providers.ts (ticket 01)
- [x] Factory auto-selects: `SARVAM_API_KEY` set → Sarvam; otherwise → Web Speech API — factory.ts (ticket 01)
- [x] Sarvam missing key → throws clear config error at factory init — factory.ts + config.server.ts z.refine (ticket 01)
- [x] Web Speech unavailable (Firefox, etc.) → throws clear error — providers.ts + client.test.ts
- [x] Client-side provider: `getSTTClientProvider()` returns `WebSpeechSTTProvider` for browser use — config.ts + client.test.ts
- [x] Tests: mock provider used; unknown/unsupported provider errors covered; provider switching via env — factory.test.ts, client.test.ts, voice-integration.test.ts