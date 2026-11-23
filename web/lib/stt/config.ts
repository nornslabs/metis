import type { STTProviderName } from "./types";
import { WebSpeechSTTProvider } from "./providers";
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
 * Client always uses Web Speech API (free, no key, built into Chrome/Edge/Safari).
 * Sarvam is server-only (requires SARVAM_API_KEY which must not be shipped to the client).
 */
export function getSTTClientProvider(): STTProvider {
  if (typeof window === "undefined") {
    throw new Error("getSTTClientProvider can only be used on the client");
  }

  if (!("SpeechRecognition" in window || "webkitSpeechRecognition" in window)) {
    throw new Error("Web Speech API is not available in this browser");
  }

  return new WebSpeechSTTProvider();
}
