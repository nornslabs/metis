# 05: Error Handling, Polish & Cross-Device

**What to build:** End-to-end resilience and polish across the voice feature. Handles every failure mode gracefully with clear user feedback and text fallback. Verifies mobile + desktop behavior.

**Blocked by:** 03 (Chat Input Integration), 04 (Sarvam STT Provider + Web Speech API Fallback)

**Status:** ready-for-agent

- [ ] Mic permission denied → toast "Microphone access denied. You can still type." + voice button stays visible but disabled-with-tooltip
- [ ] Sarvam API error (401/429/500) → toast "Transcription failed. You can still type." + input untouched
- [ ] Web Speech API not available (browser doesn't support it) → hide voice button + tooltip "Voice input not supported in this browser"
- [ ] Empty audio / silence → "Nothing heard" toast, no crash
- [ ] Auto-stop on ~2s silence after user stops speaking
- [ ] Cross-device: touch targets ≥44px on mobile, works in Safari iOS and Chrome Android
- [ ] E2E tests: happy path speak→transcript→submit→agent respond; each failure path; mobile viewport
- [ ] No hardcoded strings — all UI text from config/i18n-ready constants