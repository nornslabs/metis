# 02: Voice Recording UI Component

**What to build:** Microphone button in the chat input bar (prominent, "voice first" positioning). Press to start recording, press again to stop (or auto-stop on ~2s silence). Visual feedback: recording indicator (red destructive button), audio level meter. Outputs a `Blob` (WebM/Opus) when stopped. Uses `navigator.mediaDevices.getUserMedia({audio: true})` + `MediaRecorder`.

**Blocked by:** 01 (STT Adapter Pattern) — needs the provider interface to know the audio format contract

**Status:** ready-for-agent

- [x] Mic button renders in chat input (destructive when recording, default when idle)
- [x] Click → requests mic permission → starts MediaRecorder → shows recording UI
- [x] Second click → stops recorder → resolves with `Blob`
- [x] Recording indicator: destructive button + MicOff icon
- [x] Audio level meter: animated bars reflecting input volume
- [x] Permission denied → toast "Microphone access denied. You can still type."
- [x] Auto-stop on ~2s silence (configurable via `silenceTimeoutMs`)
- [x] Mic tracks released on stop
- [x] Component tests: render, permission flow, recording lifecycle, blob output format (WebM/Opus)
- [x] Works on mobile Safari/Chrome and desktop (responsive, touch-friendly)

**Files added:**
- `web/lib/stt/voice-recorder.ts` — `VoiceRecorder` class managing MediaRecorder lifecycle (platform-agnostic, no React)
- `web/lib/stt/voice-recorder.test.ts` — 6 unit tests covering all recording paths
- `web/lib/stt/use-voice-recorder.ts` — `useVoiceRecorder` React hook wrapping VoiceRecorder
- `web/components/chat/voice-button.tsx` — `VoiceButton` component + `AudioLevelMeter`

**Verification:** `npx vitest run` → 292/292 tests pass; `npx tsc --noEmit` → clean.

**Provider selection (from ticket 01):** `STT_PROVIDER=sarvam` → Sarvam (requires `SARVAM_API_KEY`); otherwise → Web Speech API (free, no key); `mock` for tests.
