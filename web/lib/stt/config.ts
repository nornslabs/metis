import type { STTProviderName } from "./types";
import { WebSpeechSTTProvider, MockSTTProvider } from "./providers";
import type { STTProvider } from "./types";

/** Client-safe STT config: provider name only, no secrets. Safe to import from client components. */
export function getSTTClientConfig(): { provider: STTProviderName } {
  // Provider selection happens server-side via getSTTProvider() reading STT_PROVIDER.
  // The client config defaults to web-speech (the free fallback); the server side
  // may override with sarvam when SARVAM_API_KEY is configured.
  return { provider: "web-speech" as STTProviderName };
}

/** Returns the STT provider for client-side use.
 *
 * Provider selection:
 * - `web-speech` -> WebSpeechSTTProvider (free, browser built-in, no key)
 * - `sarvam` -> throws (Sarvam API key is server-only; use the server STT endpoint)
 * - `mock` -> MockSTTProvider (tests only)
 *
 * Throws a clear error if the selected provider cannot be used client-side.
 */
export function getSTTClientProvider(providerName: STTProviderName = "web-speech"): STTProvider {
  if (typeof window === "undefined") {
    throw new Error("getSTTClientProvider can only be used on the client");
  }

  if (providerName === "sarvam") {
    throw new Error(
      "Sarvam STT requires server-side configuration. Set STT_PROVIDER=web-speech or configure Sarvam in Settings.",
    );
  }

  if (providerName === "mock") {
    return new MockSTTProvider();
  }

  if (!("SpeechRecognition" in window || "webkitSpeechRecognition" in window)) {
    throw new Error("Web Speech API is not available in this browser");
  }

  return new WebSpeechSTTProvider();
}
