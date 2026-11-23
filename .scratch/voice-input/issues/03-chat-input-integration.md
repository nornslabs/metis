# 03: Chat Input Integration

**What to build:** Wire the voice recording component (02) into the existing chat input flow. When recording stops, send the audio blob to the STT adapter (01), get the transcript, populate the text input field so the user can review/edit before sending, then submit via the existing message pipeline (same as typed text).

**Blocked by:** 02 (Voice Recording UI Component) — needs the recording component and STT adapter

**Status:** ready-for-agent

- [x] Voice component's `onBlob` callback calls `getSTTClientProvider().transcribe(blob)` — wired in `RunConversation`
- [x] Transcript text appears in the chat input field via `form.setValue("text", transcript)` (user can edit before Enter)
- [x] Empty transcript → no-op, shows "Nothing heard. Try again." toast
- [x] STT error → toast "Transcription failed. You can still type." + input stays usable
- [x] Submitting voice-transcribed message goes through identical flow as typed message (same `form.handleSubmit`, same API)
- [x] Integration tests: provider returns transcript, empty transcript no-op, STT error → toast
- [x] No new API routes or server changes — reuses existing message submission

**Files added/modified:**
- `web/lib/stt/config.ts` — added `getSTTClientProvider()` returning `WebSpeechSTTProvider` for client-side use
- `web/lib/stt/client.test.ts` — 4 tests for client provider selection
- `web/lib/stt/voice-integration.test.ts` — 5 tests for WebSpeechSTTProvider onresult/onerror flows
- `web/components/chat/composer.tsx` — added `voice` prop to `ComposerProps`, rendered in action bar
- `web/components/chat/run-conversation.tsx` — wired `VoiceButton` with `onBlob` handler that transcribes + `form.setValue`

**Verification:** `npx vitest run` → 301/301 tests pass; `npx tsc --noEmit` → clean.
